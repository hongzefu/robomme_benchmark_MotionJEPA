# 0926 方案：`src/robomme_hard/` 独立包 + `scripts/evaluation_hard.py` 接口重构（只规划不实施）

> **权威性**：本文件是「把 V6 新难度链路拆成独立包 `robomme_hard`、原包 `robomme` 回到上游原样」的实施方案；只规划，不实施，每一阶段须用户单独批准后才动手。**本方案与 P1（`scripts/` 顶层五入口冻结）、P2（`src/robomme/` 逐个批准）直接相关。**
> **第三轮修订（2026-09-27，现行）**：拆包形态由「整包复制」改为「分层继承」，生成链路由四步改为两阶段 `scripts/injection-dev/`，jsonl 增加回写块。**现行方案全文在第一部分 §〇′（含技术细节）**；第一部分 §一～§三、第二部分 §一～§二、附录 A §五～§七是前两轮内容，保留原文供追溯，与 §〇′ 冲突处一律以 §〇′ 为准。阶段 0b（§0.3）已实施完毕，不受本轮影响。
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `bcd7d08`（12.194；2026-09-27 更新，原初稿锚点 `716f992`／12.174；工作区在途改动见红线 R7）；生产源码含审查修复 `ca32e9b`（12.188）；V5 原始锚点 `da77662`；V1 基线 `13e5151`；上游 `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`（2026-09-26 `git ls-remote` 实测）。
> **工作副本**：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（环境 A，sled-vail）。上游只读快照在会话 scratchpad `upstream/`（浅克隆，用后即弃，实施时按第二部分 §2.1 重新取）。
> **commit 体例**：`<大>.<小>[.<修订>] <中文描述>`，第三轮修订的计划文件本身为 12.204，实施从 12.205 起编号。
> **前置状态（2026-09-27）**：`0925-newtask-release-v6-plan.md`（S0～S5）与 `0926-v6-audit-fix-plan.md`（8.4 四步）均已完成，本方案进入可实施状态；细节见第一部分 §〇。
> **依赖锚点**：`uv.lock` / `pyproject.toml` 现状不变；本方案唯一的依赖侧改动是 `[tool.hatch.build.targets.wheel].packages` 增加 `src/robomme_hard`。
> **对话来源**：用户 2026-09-26 转贴的与合作者的对话（逐字保留在第一部分 §一），本方案是对该对话「能否实现、怎么实现」的回答。

# 第一部分（给人看）

> 2026-09-27 修订：按用户要求，第一部分只讲三件事——①env make 的接口；②`src/robomme` → `src/robomme_hard` 的文件级清单（哪些原样继承、哪些要加东西）；③三个脚本阶段（生成 json、生成规格与轨迹、评估）各自怎么把参数传进 env make。原第一部分的对话原话、逻辑链条、裁决项、验收表全部移到第二部分附录 A，内容不变。文件级事实以 2026-09-27 `git fetch` 上游 `main` 后 `git diff --name-status FETCH_HEAD HEAD -- src/robomme` 实测为准（FETCH_HEAD = `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`，本地 HEAD = `57fe972`）。

## 〇、前提实施与交付已完成；拆包仍待裁决，legacy 归档须先补齐依赖与证据保留清单（2026-09-27，两轮修订）

> 修订记录：第一轮（12.195/12.197）写入前置完成状态与 legacy 清单；第二轮按 Codex 审计（锚点 `e9ff7a2`，五条全部核实成立）与用户裁决改写。用户裁决原话：「我要的是归档V6 之前的 不再做对拍也不再生成 只作为经验教训」「robomme_hard 重跑 144 局与 S0 基线比 sha 这个是要保留的！并且需要wrap up成新的 …/scripts/parity负责对拍」「其他同意 修改计划」。

### 0.1 完成证据（判定行原文，不改述）

| 前置计划 | 状态 | 判定行 / 证据 |
|---|---|---|
| `0925-newtask-release-v6-plan.md` §5.3 S0～S5 | 完成 | S3 原三档 144 局：`NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0`（跑在 `c8c06ab`，**审查修复之前**）；S4 55 格 165 成功局；[最终报告](docs/validation/newtask-v6/20260926-final.md) |
| `0926-v6-audit-fix-plan.md` 8.4 四步 | 实施与 165 局交付完成；**语义验收仍有证据缺口** | 14 项 `src/robomme` 改动落地于 `ca32e9b`（12.188）；G1 `RESET_PARITY_NATIVE=PASS resets=48 sha_mismatch=0`；G2 `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0 declared_deltas=6`；165 局重生成为 `v6-02`，`S4_DELIVERY=PASS cells=55 successes=165 shortfall=0`；第二节 10 项检查 `failed=0`，但汇总行原文是 `SEMANTIC_SUMMARY=FAIL checks=10 failed=0 episodes_read=165 read_errors=3`（三个失败局的空 H5 被枚举），且 `PEG_NEARFAR=REPORT episodes=3` 对不上计划要求的 `PASS candidates=10`。两个缺口不阻塞拆包，V1′ 留档须原样带出；[留档](docs/validation/newtask-v6/20260927-audit-fix.md) |

### 0.2 对本方案的影响

1. **D-4 已满足**：S3 结论已出，「不改 `src/robomme/`」的时间锁解除；阶段 5 仍排在 V1′ 之后（红线 R1）。
2. **V1′ 保留（用户明令），且分量加重**：S3 跑在 `c8c06ab`，审查修复 `ca32e9b` 之后原三档只做过 48 次 reset 零漂移，**没有做过 144 局轨迹对拍**；V1′ 兼任修复后首次全量轨迹对拍。**V1′ 由新入口 `scripts/parity/hard_parity.py` 承担**（第二部分 §2.2），不再依赖 `artifacts/…/run_s3.py`。V1′ 是本方案唯一的生成预算（144 次轨迹尝试，阶段 1 一次申请）。
3. **legacy 口径改为「V6 之前的全部归档为经验教训」**：不再做 V2～V5 任何对拍与生成；相关代码、测试、配置、产物只有两种去处——经验教训文本进 `docs/`，其余删除（跟踪文件留 git 历史；`artifacts/` 未跟踪文件的唯一副本就是搬进 `docs/` 的那份）。V6 自己的中间产物同样只留现行交付。细则见 §0.3 与附录 B。
4. **现行规格是 `v6-02`**：包内 `env_metadata/xhard{1..4}/specs.jsonl` 从 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl` 复制（260 K / 280 K / 301 K / 367 K）；`SPECS_IDENTITY` 与 `v6-02` 比。附录 A 里的 `v6-01` 以本节为准。
5. **数字勘误**：`scripts`+`tests` 引用 `robomme` 的文件 60 个；`src/robomme` 绝对 import 7 文件；对上游 `1fadc0e` 为 26 个 .py 改、9 个 .py 新增、4 份 train 元数据改。
6. **D-1～D-3 与 V1′ 预算已裁决（用户 2026-09-27 原话「同意 修改方案」，针对上一轮列出的四项）**：D-1 放行 `scripts/evaluation_hard.py` 为顶层入口（P1 在阶段 0b 删 `generate_dataset_newseed.py` 后为四入口，阶段 3 落 `evaluation_hard.py` 后为五入口：`dataset_replay.py`、`evaluation.py`、`evaluation_hard.py`、`run_example.py`、`seed_layout.py`）；D-2 `robomme_hard` 整包 copy、零跨包 import；D-3 四个 Unmask 系 train 元数据 400 条只留 `robomme_hard/env_metadata/train/`，`robomme` 回上游 100 条；V1′ 144 次轨迹尝试预算一次性授权（P3），不加 reset、不加 rollout，FAIL 时的 `--env-package robomme` 对照侧仍须另批。**阶段 1「裁决」到此完成，实施从阶段 0b 开始，不再逐阶段重问。**

### 0.3 阶段 0b：legacy 归档与删除（拆包前做；执行顺序即下列编号）

目标：`scripts/` 与 `tests/` 里只剩 V6 四阶段 + V1′ 的闭包（附录 B 表 0），其余按「教训进 docs、其余删」处置。放在拆包前的理由：阶段 3 的 import 机械替换从 60 个文件缩到约 30 个。

| # | 步骤 | 判据 |
|---|---|---|
| 1 | **解依赖**：`scripts/parity/v4_specs.py` 内联 `canonical_json`/`digest`（原在 `scripts/injection/candidates/io.py`）；`tests/lightweight/test_v4_specs.py` 的 import 改为 `from scripts.parity.v4_specs import canonical_json`（审计第 2 条） | `grep -rn "scripts\.injection" scripts tests --include=*.py` 零命中 |
| 2 | **改默认路径**（审计第 5 条）：`scripts/parity/v6_site_catalog.py::--delivery` 默认改为 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`；`grep -rn "s4-launch\|newtask-v6/v6-01\|v6-s3-20260926-01" scripts tests` 逐处改写；重跑 `test_v6_site_labels.py`、`test_v6_site_v11.py` | 零残留、两测试通过 |
| 3 | **下沉 V1′ 运行器**：新建 `scripts/parity/hard_parity.py`（§2.2），从 `artifacts/newtask-v6/v6-s3-20260926-01/run_s3.py` 搬「1 条冒烟 + 143 条、逐局 H5 身份/终态校验、30 分钟无进展/4 小时硬上限、`compare`」逻辑，去掉绝对路径，加 `--env-package {robomme,robomme_hard}` 与 `--base`/`--manifest`/`--official-root`/`--output` 参数（审计第 3 条）；`--dry-run` 只打印命令 | `--dry-run` 输出与 S3 实际命令逐字相同；单测覆盖参数解析与 H5 校验反例 |
| 4 | **生成保留清单**（审计第 4 条）：新建只读脚本 `scripts/parity/legacy_keep_list.py`，输入 ①`docs/validation/**`、`docs/ledger/**`、三份 0925/0926 计划里出现的全部 `artifacts/…` 路径串（实测唯一路径 949 个）②显式验收依赖：`s0/lightweight-baseline.log`、`s0/lightweight-shards/**`（含 `v6-final-identities.txt`）、`s4-launch/verification/*.json`、`s4-launch/recovery/approval.json`、`s4-launch/incident/**`、`v6-s3-20260926-01/{run_s3.py,compare/summary.json,handoff-prep/production-session-*/{outcome,final_verification}.json}`、`audit/*/{审查汇总.md,verify/**,records/**}`、`v6-01/**/final-delivery.json` ③类型白名单 `.md/.json/.jsonl/.txt/.log/.sh/.py`。被引用但 >1 MiB 的非媒体文件也保留并单列；`.h5/.mp4/.png/.jpg/.npy` 一律不搬 | `LEGACY_KEEP=PASS referenced=<n> resolved=<n> missing=0`；`missing` 非零即停交用户 |
| 5 | **归档**：按清单复制到 `docs/validation/<版本>/records/legacy/<原二级目录>/…`（`newtask-v4`→v4、`newtask-v5`→v5、`newtask-v6/*` 与 `audit/*`→v6），写 `MANIFEST.md`（原路径、新路径、字节、sha256）；三份旧计划 `0921/0922/0924-newtask-release-v{3,4,5}-plan.md` `git mv` 到 `docs/plans/` 并改 docstring/测试注释里的链接；`docs/validation/newtask-v2～v5/` 原地保留 | `LEGACY_ARCHIVE=PASS copied=<n> bytes=<b> sha_mismatch=0` |
| 6 | **删跟踪文件**（附录 B 表 A 全部 + 表 B 的跟踪项）：`git rm` 逐路径；`generate_dataset_newseed.py` 一并删，P1 改四入口（`AGENTS.md` P1、`CLAUDE.md` 核实清单计数同步） | `uv run --no-sync python -m pytest --collect-only -q tests/lightweight tests/dataset` 收集错误 0；`ls -1 scripts/*.py` = 4 |
| 7 | **重采 LIGHTWEIGHT 基线**：删后按 V6 §5.3 四片口径跑一次，失败/错误身份写 `artifacts/newtask-v6/hard-split/lightweight-baseline-0b.txt`；阶段 3 的 `LIGHTWEIGHT=PASS new_failures=0` 以它为分母（S0 的 46/12 含已删测试，不再适用） | 四片各 ≤280 s |
| 8 | **删 `artifacts/` 大目录**（单独 commit，body 记 `du`/`df`）：附录 B 表 B 所列目录逐个显式列名，不用 glob；删前 `du -sh` 逐目录、删后 `df -h /data` | 附录 B 表 C 的保留目录一个不少 |

红线：`artifacts/` 删除逐目录显式列名（正本第 14 条）；D 组（他人在途）不读不删；步骤 4、5 未 PASS 不得进入 6、8。

#### 0.3.1 阶段 0b 实施结果（2026-09-27，追加，不改上表）

| 步骤 | commit | 判定行 / 实测 |
|---|---|---|
| 1～3 | 12.200 | `grep scripts.injection` 仅剩待删文件；站点测试 16 passed；`tests/lightweight/test_hard_parity.py` 9 passed（含 dry-run 与 S3 两条 run 命令逐字相同） |
| 4～5 | 12.201 | `LEGACY_KEEP=PASS referenced=1168 resolved=974 missing=0 absent_before=194 files=3409 large=0 bytes=64469896`；`LEGACY_ARCHIVE=PASS copied=3409 bytes=64469896 sha_mismatch=0`；显式项 `audit/*/records/**`、`v6-01/**/final-delivery.json` 从未存在，记 `OPTIONAL_ABSENT` |
| 6～7 | 12.202 | `ls -1 scripts/*.py` = 4；collect-only 1329 条、错误 0；四片 8/5/127/47 s，4 failed 均属 S0 基线、0 errors，基线 `artifacts/newtask-v6/hard-split/lightweight-baseline-0b.txt` |
| 8 | 12.203 | 31 目录 `RM_OK`、两审查 worktree `git worktree remove`；表 C 七个保留目录全在；`/data` 可用 536G → 833G（94%） |

与上表不同之处：`docs/validation/newtask-v2/` 保留（依步骤 5「原地保留」）；`INJECTION_REFACTOR_PLAN.md`、`NEWTASK_V2_PLAN.md` 移入 `docs/plans/` 而非删除；另删两份孤儿测试 `test_parallel_calibration.py`、`test_episode_action_sampling.py`。

## 〇′、第三轮修订（2026-09-27）：分层继承的双包 + 两阶段 `scripts/injection-dev/` + 可回写的单一 jsonl（现行方案，含技术细节）

> **授权边界**：本节只规划不实施。实施按 §〇′.9 阶段表逐阶段进行；阶段 3（`src/robomme` 回退）触碰 P2，须用户逐个批准；阶段 4 的生成预算按 §〇′.8 一次性申请。
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `7c7118fa`（12.203，阶段 0b 收尾）；上游 `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`；官方隔离源码树 `artifacts/train-parity/local-smoke-01/official-src/`（`.official_tree` = `1d4c13697f0c5fbd7a8b05e01c196c984a07406c`，是 tree sha 不是 commit sha，两者对应关系阶段 0 用 `git rev-parse 1fadc0ec^{tree}` 核实）；现行规格 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（xhard1/2/3 各 130 行 + header，xhard4 160 行 + header，selected 行合计 165）；S4 交付清单 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`。
> **本节体例**：本轮改动含代码，按正本第 2 条应分两部分；为避免与前两轮的第二部分交错，本节把「给人看」(§〇′.0～§〇′.8) 与「技术细节」(§〇′.9～§〇′.12) 合在同一节内顺序排列，前者内联全部关键锚点与判定行，后者只补前者没有展开的实现细节。

### 〇′.0 用户原话与已定口径

本轮对话（2026-09-27）中用户的关键指令，按时间顺序逐字保留：

| 编号 | 原话 | 落到哪一条口径 |
|---|---|---|
| Q1 | 「能否改为两阶段 第一阶段 定规则 抽签 封存 只留一个jsonl 第二阶段 生成h5 这两阶段所有依赖全部放入 …/scripts/injection-dev」 | E-1、E-2 |
| Q2 | 「…/scripts/parity这里负责用同样的方式 生成easy medium hard的16*3*3 并且进行对拍」 | E-9（取 A 解读，用户后续「其他都同意」） |
| Q3 | 「是否能实现 …/episode_config_resolver.py …/evaluation.py benchmarkenvbuilder也会读取这一个jsonl 第一阶段 定规则 抽签 封存 只留一个jsonl这里走另外的方式 全部在 …/scripts/injection-dev这里实现 让用户只能看到一个定死的jsonl？」 | E-6、E-7 |
| Q4 | 「第二阶段 生成h5 应该也只看jsonl 但是还要回写」 | E-3 |
| Q5 | 「同意 …（第一阶段合成一个入口）这里只留内存 不要写入文件」 | E-2 |
| Q6 | 「jsonl本身 放入 …/src/robomme/env_metadata这里 这样和之前的接口一致？」 | E-6（落点最终为 `src/robomme_hard/env_metadata/`，见 E-4 双包） |
| Q7 | 「是否可以用双包 但是尽可能继承的模式？详细讲清楚」 | E-4 |
| Q8 | 「robomme_hard 可单向 import robomme 的非注册模块同意 test可以先不管 xhard 侧的回归需要加入 另外是否可以加入更强的sha256或者commit校验没改动src robomme 环境类能否不要同名？… 我更倾向做法c 继续细化方案 从头开始讲」 | E-4、E-5、E-8、E-11、E-12 |
| Q9 | 「同 id可以」 | E-5 |
| Q10 | 「generate_dataset.py进git 其他都同意 写完整计划」 | E-10 及 §〇′.0 全部待定项 |

**已定死口径**（每条注明依据小节）：

- **E-1 两阶段生成链路**：第一阶段「定规则 + 抽签 + 封存」一个入口只产出一份 `specs.jsonl`；第二阶段「生成 h5」只读这份 jsonl。全部依赖放 `scripts/injection-dev/`（§〇′.5）。
- **E-2 第一阶段中间量只在内存**：`sampling_config` 与 drafts 不再落盘；规则全文与抽签统计（`draw_stats`）写进 jsonl header（§〇′.5.1）。
- **E-3 第二阶段回写**：每行增加 `rollout` 块（结果、递补、产物指纹、包指纹）；`identity_sha256` 只覆盖 header 规则部分与各行 `spec` 块；递补用「追加行 + 标记」，不改不删原行（§〇′.5.3）。
- **E-4 双包 + 分层继承（做法 C）**：`src/robomme/` 回官方原样；`src/robomme_hard/` 只放差异——16 个环境类与被改过／新增的 utils **复制**，未改过的 utils 与 wrapper **借用**（单向 import `robomme`），`BenchmarkEnvBuilder` **子类化**；`robomme_hard` 借用的每个文件必须与官方 sha 相同（§〇′.2）。
- **E-5 环境类同 id**：16 个环境仍注册为 `"BinFill"` 等官方 id；`robomme_hard` 的副本一律 `@register_env(<id>, override=True)`，并在包导入末尾断言注册表归属（§〇′.2.3）。
- **E-6 jsonl 落点**：`src/robomme_hard/env_metadata/xhard{1,2,3,4}/specs.jsonl`，一档一目录一份，与官方 `env_metadata/<dataset>/` 形状一致（§〇′.6）。
- **E-7 评估只看 jsonl**：`HardBenchmarkEnvBuilder(env_id, dataset="xhard3")` 自己读包内 jsonl；`scripts/evaluation.py` 与官方逐字节相同不动，`scripts/evaluation_hard.py` 为第五入口（D-1 已放行）（§〇′.6）。
- **E-8 G1 强校验**：钉官方 40 位 commit + 逐文件 sha256 清单 `src/robomme_hard/UPSTREAM.json` + 守卫脚本 `scripts/parity/upstream_guard.py` + 导入时 cheap 档校验（§〇′.3）。
- **E-9 `scripts/parity/` 职责取 A**：只做「与官方比」——S0 基线原三档 sha 对拍（`train_split_parity.py`）、V1′（`hard_parity.py`）、G1 守卫、xhard 侧回归；**不**让原三档再过一遍抽签→回注（§〇′.7）。
- **E-10 官方执行代码进 git**：`generate_dataset.py` 及其三个兄弟依赖 vendor 到 `scripts/parity/official/`，记来源 commit 与逐文件 sha（§〇′.7.2）；`--official-root` 参数保留但默认指向 vendor 目录。
- **E-11 `tests/` 先不管**：只保证 `--collect-only` 零 import 错误；测试语义修复另立任务。
- **E-12 xhard 侧回归加入**：`HARD_RESET_REPLAY`（55 次回注 reset）+ `HARD_ROLLOUT_SHA`（16 局）+ `HARD_EVAL_SMOKE`（1 局），预算一次申请（§〇′.8）。
- **E-13 D-3 维持**：四个 Unmask 系 train 元数据 400 条只留 `robomme_hard/env_metadata/train/`，`robomme` 回官方 100 条。
- **E-14 `RecordWrapper.py` 不子类化而复制**：`fail_safe_limit` 是 `step()` 方法内部的字面量（`RecordWrapper.py::RobommeRecordWrapper.step`，约 310 行），子类覆写等于整段复制，直接复制文件更诚实（§〇′.2.1）。

### 〇′.1 要保证什么

| 编号 | 保证 | 靠什么 | 判定行 |
|---|---|---|---|
| G1 | `src/robomme/**` 与官方 `main` 逐字节相同 | 钉 commit + sha256 清单 + 守卫脚本（§〇′.3） | `UPSTREAM_BYTES=PASS commit=<sha> files=<n> diff=0 borrowed=<m>` |
| G2 | `robomme_hard` 跑原三档，h5 与官方 S0 基线 sha 逐位相同 | V1′ 144 局（§〇′.7.1） | `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144` |
| G3 | `robomme_hard` 跑 xhard 四档，与 S4 交付一致 | xhard 侧三道闸门（§〇′.8） | `HARD_RESET_REPLAY=PASS resets=55 mismatch=0`、`HARD_ROLLOUT_SHA=PASS compared=16 sha_equal=16`、`HARD_EVAL_SMOKE=PASS` |
| G4 | 合作者只看到一份定死的 jsonl，接口与 `dataset="test"` 一致 | `HardBenchmarkEnvBuilder`（§〇′.6） | `SPECS_IDENTITY=PASS tiers=4 rows=550 selected=165`、`EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| G5 | 同进程内 16 个环境 id 的归属唯一且可查 | `override=True` + 导入守卫 + 注册表归属断言（§〇′.2.3） | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` |
| G6 | 两阶段链路只依赖 jsonl，中间量不落盘，回写不破坏封存 | §〇′.5 | `FREEZE_ONLY_JSONL=PASS files_written=1`、`ROLLBACK_WRITE=PASS spec_hash_unchanged=1` |

### 〇′.2 包结构与分层继承

#### 〇′.2.1 目录与每个文件的来路

```text
src/robomme/                          官方 main 原样（G1）；本仓库不再放任何自有文件
src/robomme_hard/
  __init__.py                         导入守卫 + 先注册自家环境 + 注册表归属断言（§〇′.2.3）
  UPSTREAM.json                       官方 commit、tree、src/robomme 逐文件 sha256、借用清单（§〇′.3）
  README.md                           §〇′.11
  robomme_env/
    __init__.py                       复制自现 src/robomme（16 行 from .X import *）
    <Task>.py × 16                    复制；装饰器改 @register_env("<id>", override=True)；绝对 import 按 §〇′.2.2 规则改
    utils/
      __init__.py                     复制
      改过的 8 个：difficulty.py object_generation.py route.py segmentation_utils.py
                  subgoal_language.py task_goal.py subgoal_planner_func.py vqa_options.py     复制
      新增的 9 个：bin_collision.py episode_spec.py sampling_config.py swap_uniform.py
                  unmask_distractor_sampler.py unmask_distractors.py unmask_swap_xhard.py
                  xhard.py xhard_home_site.py                                                复制
      未改的约 15 个（adjacent.py choice_action_mapping.py constant.py obschange.py
                  oracle_action_matcher.py planner_denseStep.py planner_fail_safe.py reset_panda.py
                  rpy_util.py save_reset_video.py SceneGenerationError.py statechange.py
                  task4recovery.py generate_sample_action.py subgoal_evaluate_func.py）       借用：三行别名 shim（§〇′.2.2）
      planner-ref.py、"vqa_options copy.py"                                                  不搬（文件名不可 import，官方遗留）
  env_record_wrapper/
    __init__.py                       自家：RobommeRecordWrapper（复制版）、BenchmarkEnvBuilder（子类）、hard_specs；
                                      借用：from robomme.env_record_wrapper import DemonstrationWrapper,
                                            EndeffectorDemonstrationWrapper, FailAwareWrapper,
                                            MultiStepDemonstrationWrapper, RRTPlanFailure, <episode_dataset_resolver 导出项>
    RecordWrapper.py                  复制（+7 行 fail_safe_limit 5000；E-14）
    OraclePlannerDemonstrationWrapper.py   复制（内容同官方，但它 import 的 vqa_options 是改过的，须指向 robomme_hard）
    hard_builder.py                   class BenchmarkEnvBuilder(robomme.env_record_wrapper.BenchmarkEnvBuilder)（§〇′.6）
    hard_specs.py                     load_specs 与封套校验（从 scripts/parity/v4_specs.py 下沉）
  env_metadata/
    xhard1/specs.jsonl … xhard4/specs.jsonl
    train/record_dataset_{ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap}_metadata.json   400 条（E-13）
pyproject.toml                        [tool.hatch.build.targets.wheel].packages 加 "src/robomme_hard"
```

按层归纳：

| 层 | 做法 | 文件数（约） | 为什么这样选 |
|---|---|---|---|
| 环境类 | 复制 | 16 | xhard 改动交错在 `_load_scene` / `_initialize_episode` 等几百行方法内（`BinFill.py` 1120 行里 98 处），继承只能整段覆写，无收益 |
| 改过／新增的 utils | 复制 | 8 + 9 | 与官方不同，必须自有 |
| 未改的 utils | 借用（shim） | 15 | 单一真源；改动零，官方更新自动跟随 |
| 未改的 wrapper | 借用（re-export） | 6 | 同上 |
| `RecordWrapper.py` | 复制 | 1 | E-14 |
| `BenchmarkEnvBuilder` | 子类 | 1 新文件 | 改动就是「多认四个档名 + 读 jsonl + 拼三个 kwargs」，官方各方法都很短，适合覆写 |
| `hard_specs.py` | 新增 | 1 | 本来就是新的 |

对比第二轮「整包复制」：`robomme_hard` 自有 `.py` 从 72 个降到约 38 个（16 + 17 + 1 + 1 + 1 + 1 + `__init__` 若干），其余全部指向 `robomme`。

#### 〇′.2.2 借用的实现与 import 改写规则

**为什么不能直接 `from robomme.robomme_env.utils.rpy_util import …`**：Python 导入子模块前先执行父包 `__init__`，而 `robomme/robomme_env/__init__.py` 就是 16 行 `from .BinFill import *`——任何一次借用 utils 都会顺带把官方 16 个环境注册进 ManiSkill 注册表。这不是障碍（见 §〇′.2.3 的 `override=True`），但决定了「借用」必须与「注册表归属」一起设计，不能只看 import 语句。

**shim 写法**（每个借用的 utils 模块一个同名文件，三行，不含逻辑）：

```python
# 借用：本模块是 robomme 同名模块的别名，逻辑以官方为准；借用清单见 ../../UPSTREAM.json
import importlib, sys
sys.modules[__name__] = importlib.import_module("robomme.robomme_env.utils.rpy_util")
```

复制进来的环境文件写的是相对 import（`from .utils.rpy_util import …`），解析到 `robomme_hard.robomme_env.utils.rpy_util` 即命中 shim，拿到的就是官方模块对象。这不是对 `robomme` 的覆盖（不改 `robomme` 任何模块的行为），只是 `robomme_hard` 自己命名空间里的别名。

**绝对 import 改写规则**（对 §〇′.2.1 里每个「复制」文件逐行 AST 检查，阶段 1 出清单）：

| 复制文件里出现的 | 处理 |
|---|---|
| 相对 import（`from .utils.x`、`from ..robomme_env.utils.y`） | 不动；由 shim 或自有副本承接 |
| `from robomme.<path> import …`，且 `<path>` 在借用清单内 | 不动（就是要借用） |
| `from robomme.<path> import …`，且 `<path>` 是改过／新增的 | 改成 `from robomme_hard.<path> import …`——漏一处就静默回头用官方旧逻辑，这是本方案唯一容易漏的洞 |

现状扫描（第二轮 §2.1／2.2）：绝对 import 共 7 个文件，其中 `OraclePlannerDemonstrationWrapper.py`、`RecordWrapper.py`（`step` 内延迟 import `vqa_options`）、`subgoal_planner_func.py`、`vqa_options.py`、`generate_sample_action.py`、`subgoal_evaluate_func.py`、`vqa_options copy.py`；按上表，指向 `vqa_options` 的全部要改，其余按清单判定。判定行 `ABS_IMPORT=PASS files=<n> retargeted=<k> borrowed=<m> stray=0`（`stray` = 指向改过模块却仍写 `robomme.` 的条数）。

#### 〇′.2.3 注册表归属：同 id 怎么做到不静默出错

**实测语义**（`.venv/.../mani_skill/utils/registration.py::register_env`）：同一 uid 第二次注册时，`override=False` → `logger.warn("Env … is already registered. Skip registration.")` 然后 **静默保留第一个**；`override=True` → 弹出旧登记并重新注册。也就是说，若什么都不做，谁先 import 谁赢，输的一方连异常都没有——这正是「同 id」最危险的地方。

**三道机制**：

1. **`override=True`**：16 个复制进 `robomme_hard` 的环境文件，装饰器改为 `@register_env("BinFill", override=True)`（16 处、每处一个参数）。效果：只要进程里 import 过 `robomme_hard.robomme_env`，16 个 id 一律归 `robomme_hard`，与 import 顺序无关——先 import 官方再 import hard：hard 覆盖；先 hard 再官方：官方走 `Skip registration`。
2. **导入守卫**（`robomme_hard/__init__.py`）：
   ```python
   import sys, warnings
   if "robomme.robomme_env" in sys.modules:
       warnings.warn("robomme.robomme_env 已先于 robomme_hard 导入；16 个环境 id 将被 robomme_hard 覆盖", RuntimeWarning)
   from . import robomme_env as _envs          # 先注册自家 16 个（触发借用 shim 时官方也会被 import，但被 override）
   from mani_skill.utils.registration import REGISTERED_ENVS
   _foreign = [uid for uid in _envs.ENV_IDS if not REGISTERED_ENVS[uid].cls.__module__.startswith("robomme_hard.")]
   if _foreign:
       raise ImportError(f"注册表归属异常，以下 id 不属于 robomme_hard：{_foreign}")
   ```
   不再像第二轮那样一遇到官方已导入就 `raise`——因为借用本身就会导入官方包，`raise` 会把自己拦死；改为「警告 + 事后断言归属」。`ENV_IDS` 是 `robomme_env/__init__.py` 新增的 16 元组，与官方 `__init__` 的 import 顺序一一对应。
3. **包指纹进产物**：`robomme_hard` 版 `RobommeRecordWrapper` 在 h5 attrs、`hard_specs` 在 jsonl header／`rollout` 块、`HardBenchmarkEnvBuilder` 在 `info` 里都写 `env_package="robomme_hard"` 与 `package_fingerprint=<hard_fingerprint>`；对拍与评估加载时核对。装错包、混装包，在产物层面一眼可查，不会静默。

**红线改写**：第二轮「两包不可同进程导入」改为「**同进程一旦导入 `robomme_hard`，16 个环境 id 全部归它；需要官方原三档行为时另开进程只导 `robomme`**」。V1′ 本来就是用 `robomme_hard` 跑原三档，与此一致。

**不对称性写明**：守卫只在 `robomme_hard` 侧；一个只导入 `robomme` 的进程不会知道 `robomme_hard` 的存在，这是正确行为，不是漏洞。

### 〇′.3 G1 的强校验：commit、sha256、守卫

三层，从静态到运行时：

1. **`src/robomme_hard/UPSTREAM.json`**（进 git；放 `robomme_hard` 而不是 `robomme` 是为了不破坏 `robomme` 的零 diff）：
   ```json
   {"upstream": {"url": "https://github.com/RoboMME/robomme_benchmark", "commit": "1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9", "tree": "<git rev-parse commit^{tree}>"},
    "robomme_files": {"src/robomme/__init__.py": "<sha256>", "...": "..."},
    "borrowed": {"robomme/robomme_env/utils/rpy_util.py": "<sha256>", "...": "..."},
    "manifest_sha256": "<剔掉本键后 canonical JSON 的 sha256>"}
   ```
   `commit` 必须是 40 位，禁 `main`（正本第 15 条）；`manifest_sha256` 让清单自身防篡改。
2. **`scripts/parity/upstream_guard.py`**（纯 CPU、秒级，纳入核心短测）：
   - `git fetch <url> <commit>` → `git diff --stat <commit> HEAD -- src/robomme` 必须为空；网络不可达时退化为只做下面两步并把判定行标 `net=skipped`；
   - `src/robomme/**` 逐文件 sha256 与 `robomme_files` 比；文件集合必须**相等**（多一个少一个都 FAIL，含 `env_metadata/`）；
   - `borrowed` 清单每个文件 sha 必须命中，且清单里的每个模块在 `robomme_hard` 侧必须是 shim（文件 ≤ 3 行非注释行，含 `sys.modules[__name__] =`），防止有人把借用悄悄改成本地副本；
   - 判定行 `UPSTREAM_BYTES=PASS commit=1fadc0ec files=<n> diff=0 borrowed=<m> net=<ok|skipped>`。
3. **导入时 cheap 校验**（`robomme_hard/__init__.py`，`UPSTREAM.json` 加载后）：对 `borrowed` 每个文件做「字节数 + 首尾各 1 MiB blake2b」（正本第 15 条 cheap 档），不符 `warnings.warn`，不 raise——用户机器上不应被 `.pyc`、CRLF 之类无关差异拦死；显式声明 cheap 档挡不住「等长改中间字节」，full 档由守卫脚本负责。

**两段源码指纹**：现 `scripts/parity/v4_specs.py::source_fingerprint` 只盖 `src/robomme/robomme_env/**.py`。下沉到 `hard_specs.py` 后拆成 `base_fingerprint`（`borrowed` 清单文件的总 sha）与 `hard_fingerprint`（`src/robomme_hard/**.py` 去 `__pycache__` 的总 sha），两者都写 jsonl header；`load_specs` 对不符只警告（第二轮 §5.3 口径不变），因为发布后指纹本就该在打包时重算。

### 〇′.4 `scripts/` 重组后的样子

```text
scripts/
  seed_layout.py  dataset_replay.py  evaluation.py  run_example.py     四入口不动（后三者官方原样）
  evaluation_hard.py                                                    第五入口（D-1）；与 evaluation.py diff ≤ 12 行
  injection-dev/                V6 四档生产链路（§〇′.5）；不随包分发
    __init__.py
    freeze_specs.py             第一阶段入口
    generate_h5.py              第二阶段入口
    _extract.py                 原 parity/train_split_config.py::extract_task（读 native_blocks）
    _draw.py                    原 parity/v4_specs.py 的 draw 侧（_draw_one / draw_task / worker 池）
    _freeze.py                  原 parity/v4_specs.py 的 freeze 侧（选 0/3/6、哈希、header）
    _rollout.py                 原 parity/v4_rollout.py（批次编排、H4 递补、回写）
    _report.py                  原 parity/v5_generation.py 的 report 侧（只读汇总）
    site/                       v6_site.py v6_site.html v6_site_catalog.py v6_candidate_values.py
                                v6_tier_monotone.py v6_v0_native_definitions.py v6_gt_lengths.{py,json}   收尾出图，只读产物
  parity/                       只做「与官方比」（§〇′.7）
    train_split_parity.py  train_split_runner.py  train_split_worker.py  train_split_config.py
    train_split_comparison.py  train_split_audit.py  comparator_fixtures.py                   S0 基线对拍设施，不动
    hard_parity.py              V1′
    upstream_guard.py           G1（§〇′.3）
    hard_regression.py          xhard 侧回归（§〇′.8）
    official/                   vendor 的官方执行代码（§〇′.7.2）
      SOURCE.json  generate_dataset.py  validate_generated_dataset_contract.py
      write_generation_report.py  compare_joint_actions.py
    identities_16x3.txt  manifest_16x3.json  README.md
  configs/
    newtask-v3/{subset_manifest,train_manifest}.json + official_train/     parity 用，不动
    newtask-v6/v6-02/                                                       保留为「S4 生成用的那份」只读留档；jsonl 真源改为包内
    newtask-v4/  newtask-v5/  newtask-v6/{sampling_config.json,v6-01/}      删（V6 闭包外或已被包内 jsonl 取代）
```

去留判据：

| 现文件 | 去向 | 理由 |
|---|---|---|
| `parity/v4_specs.py` | 拆成 `injection-dev/_draw.py` + `_freeze.py`；`load_specs` 下沉 `hard_specs.py` | 抽签／冻结是 V6 生产链路，不是对拍 |
| `parity/v4_rollout.py` | → `injection-dev/_rollout.py` | 同上 |
| `parity/v5_generation.py` | `pipeline` 子命令废弃（两阶段入口取代）；`report` → `injection-dev/_report.py` | 同上 |
| `parity/train_split_config.py` | **留在 parity**，`injection-dev/_extract.py` 从它 import `extract_task` | S0 基线的 C／D 路也要它提取原值快照 |
| `parity/train_split_runner.py` / `train_split_worker.py` | **留在 parity**，`injection-dev/_rollout.py` 以子进程调用 | 它们是官方执行代码的镜像 worker，本质是对拍设施；两边共用一份才能保证「生产用的执行逻辑 = 对拍用的执行逻辑」 |
| `parity/v6_*.py`、`v6_site.html`、`v6_gt_lengths.*` | → `injection-dev/site/` | V6 收尾出图，只读产物 |
| `parity/legacy_keep_list.py` | 删 | 阶段 0b 一次性工具，任务已完成 |
| `scripts/eval/v4_eval.py`、`scripts/eval/__init__.py` | 删 | 被 `evaluation_hard.py` + 子类 builder 取代；`from_v4_specs` 保留为薄包装以防外部脚本引用，但仓库内不再有调用方 |
| `scripts/injection/`（空壳 + `__pycache__`）、`scripts/parity/results/`（空目录） | 删 | 阶段 0b 残留 |

`scripts/parity/__init__.py` 现在把本目录插进 `sys.path` 供裸 import；`injection-dev/` 用包 import（`from scripts.parity import train_split_config`），不再插 `sys.path`。

### 〇′.5 `scripts/injection-dev/` 两阶段

#### 〇′.5.1 第一阶段 `freeze_specs.py`

```bash
uv run --no-sync python -m scripts.injection-dev.freeze_specs \
  --tier xhard3 --tasks all --candidates-per-env 10 --select 0,3,6 \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 \
  --out src/robomme_hard/env_metadata/xhard3/specs.jsonl
```

（目录名带连字符不能作为 Python 包名直接 `-m`；实施时二选一：目录名改 `injection_dev`，或保留 `injection-dev` 并以路径直跑 `uv run --no-sync python scripts/injection-dev/freeze_specs.py`。用户已确认目录名，**默认取后者**，`__init__.py` 不做包导入、各入口自行 `sys.path.insert`；若阶段 2 实测路径直跑带来 import 混乱，改名 `injection_dev` 须回来请示。）

内存内三步，对应现有函数：

| 步 | 现有实现（搬过去不改语义） | 起不起环境 | 产物去向 |
|---|---|---|---|
| ① extract | `train_split_config.extract_task(task, release="newtask-v6")` → `{decision, native}` 合成 `sampling_config` dict | 否 | 内存；写进 header `sampling_config` |
| ② draw | `v4_specs._draw_one`（`gym.make(task, sampling_config=…, **env_kwargs(seed, episode, tier))` → `reset()` → `env.unwrapped._spec.to_dict()`）× 10 候选／格，worker 池与 GPU 轮转沿用 `_draw_worker_init` | 是（只 reset） | 内存；每格成功候选进行列表，失败次数与异常类型进 header `draw_stats[task]` |
| ③ freeze | `v4_specs.cmd_freeze` 的选行、`spec_sha256`、`identity_sha256`、封套校验 | 否 | **唯一落盘**：`--out` |

写盘用「同目录临时文件 + `os.replace`」原子替换；`--out` 已存在时默认拒绝（要 `--force`，起跑前 `ls -ld`，正本第 14 条），因为覆盖 jsonl 等于换掉四档身份。判定行 `FREEZE_ONLY_JSONL=PASS tier=xhard3 tasks=<n> candidates=<n×10> selected=<n×3> files_written=1`（`files_written` 由入口在 `tempfile` 与 `--out` 之外监控 `os.open` 计数是过度设计；实现上以「入口内除 `--out` 外不出现任何 `open(..., "w")`」的 AST 检查 + 运行后 `git status --short` 与 `find artifacts -newer` 为空作判定）。

**`--dry-run`**：只打印三步将用的参数（seed 区段、任务列表、候选数、worker／GPU 分配），与现 `v5_generation.plan_pipeline` 的 draw／freeze 命令逐项对照，是阶段 2 的等价性判据。

#### 〇′.5.2 jsonl 结构（`schema = "hard-specs/2"`）

header（第一行）在现 `v4-specs/1` 的 16 个键上做增删：

| 键 | 现状 | 本轮 |
|---|---|---|
| `schema` | `v4-specs/1` | `hard-specs/2` |
| `difficulty`、`tasks`、`per_env`、`runtime`、`seed_rule`、`select_indices`、`sampling_config`、`sampling_config_sha256`、`recovery_rule`、`identity_source`、`run_id` | 有 | 保留，语义不变 |
| `drafts_sha256` | 有 | **删**（drafts 不再存在） |
| `source_fingerprint` | 有（只盖 `robomme_env`） | 拆为 `base_fingerprint` + `hard_fingerprint`（§〇′.3） |
| `record` | 有 | 保留 |
| `draw_stats` | 无 | **新增**：`{task: {attempts, ok, failed, error_types: {ExcName: n}}}` |
| `env_package` | 无 | **新增**：`"robomme_hard"` |
| `identity_sha256` | 盖 header 全部 + 行的 `spec` | **收窄**：只盖 header 里除 `identity_sha256`、`draw_stats`、`record` 之外的键 + 每行 `{task, tier, candidate, seed, attempt, spec, spec_sha256}`；**不盖** `selected` 与 `rollout` |

行（第二行起）：

```json
{"task": "BinFill", "tier": "xhard3", "candidate": 3, "episode": 3, "seed": 12300003, "attempt": 0,
 "selected": true, "spec": {…}, "spec_sha256": "…",
 "rollout": {"status": "ok", "final_candidate": 3, "h5_sha256": "…", "frames": 412, "mp4": true,
             "duration_s": 83.1, "env_package": "robomme_hard", "package_fingerprint": "…",
             "written_at": "2026-09-27T21:04:11-04:00"}}
```

- `difficulty` 行字段改名 `tier`，`episode` 保留（= candidate，兼容 `env_kwargs`）；
- `rollout` 第一阶段产出时**不存在**（不是 `null`），`load_specs` 对缺失与存在都接受；
- `rollout.status ∈ {ok, failed, timeout}`；`failed`／`timeout` 行同样写 `h5_sha256=null` 等全部键（计数字段显式零值，P4 教训）。

#### 〇′.5.3 第二阶段 `generate_h5.py` 与回写协议

```bash
uv run --no-sync python scripts/injection-dev/generate_h5.py \
  --specs src/robomme_hard/env_metadata/xhard3/specs.jsonl \
  --output artifacts/newtask-v6/<run>/xhard3 --workers 4 --gpu 0 \
  --official-root scripts/parity/official
```

流程（沿用 `v4_rollout.cmd_run` / `_run_batch` 的批次编排，只换输入输出）：

1. `hard_specs.load_specs` 读入并做全部封套校验，记 `identity_sha256` 与每行 `spec_sha256`；
2. 取 `selected=true` 且 `rollout` 缺失或 `status != ok` 的行为待跑集（重跑已 `ok` 的行须 `--redo`）；
3. 每批写 `jobs.json` / `sampling.json` / `specs.json` 到 `--output/_rounds/round_NN/`（现有做法），子进程调用 `scripts/parity/train_split_runner.py --official-root … --env-package robomme_hard`（环境变量 `ROBOMME_ENV_PACKAGE`，worker 侧按它选 `import robomme_hard.robomme_env` 与 `from robomme_hard.env_record_wrapper import RobommeRecordWrapper`——这是 `train_split_worker.py` 唯一的非机械改动，第二轮 §2.2 已写明）；
4. **递补（H4，不变）**：某行 `failed`，从同格 `selected=false` 的候选按 `candidate` 升序取下一个，把该行 `selected` 置 `true` 并加入下一轮；原失败行 `selected` 保持 `true`、`rollout.status="failed"` 留档；每格递补上限沿用现值；
5. **回写**：全部批次结束后一次性写回——重新读 `--specs` 文件、重算 `identity_sha256`，与第 1 步记下的相等才继续（不等说明第一阶段内容被动过，拒绝回写并 `RollbackRefused` 退出）；只改 `selected` 与 `rollout`，其余字节不动；写同目录临时文件 → `os.replace`；写后再 `load_specs` 一遍，`identity_sha256` 必须仍等于写前；
6. `results.jsonl` 仍照现状写到 `--output`（供 `_report.py` 与 `hard_regression.py`），但它不再是身份来源，jsonl 才是。

判定行：`ROLLBACK_WRITE=PASS specs=<path> rows=<n> ok=<k> failed=<f> substituted=<s> spec_hash_unchanged=1`。

**中断恢复**：第 5 步是一次性写回，中途被杀不会留下半写 jsonl（临时文件 + 原子替换）；重跑时第 2 步按 `--output/_rounds/*/results.json` 复用已完成局（现 `_run_batch` 的 `round_index` 机制），不重复消耗预算（P4「恢复只处理未完成步骤」）。

#### 〇′.5.4 报告

`_report.py`（原 `v5_generation.report`）改为只读 jsonl（`rollout` 块）+ `--output` 下的 `results.jsonl`，输出 `HARD_GENERATION=REPORT tier=… ok=… failed=… substituted=…` 与 Markdown；不再需要 drafts。

### 〇′.6 `HardBenchmarkEnvBuilder` 与 `evaluation_hard.py`

`src/robomme_hard/env_record_wrapper/hard_builder.py`，类名仍叫 `BenchmarkEnvBuilder`（对外只差 import 行）：

```python
from robomme.env_record_wrapper.episode_config_resolver import BenchmarkEnvBuilder as _Upstream
from .hard_specs import load_specs
_HARD_TIERS = ("xhard1", "xhard2", "xhard3", "xhard4")
_HARD_TRAIN_OVERRIDE = {"ButtonUnmask", "ButtonUnmaskSwap", "VideoUnmask", "VideoUnmaskSwap"}   # E-13

class BenchmarkEnvBuilder(_Upstream):
    def __init__(self, env_id, dataset="test", action_space="joint_angle", max_steps=1300, override_metadata_path=None):
        self._hard = None
        if dataset in _HARD_TIERS:
            header, rows = load_specs(_PKG_METADATA / dataset / "specs.jsonl")
            self._hard = _bind(env_id, header, rows)          # 只取 task==env_id 且 selected 且 rollout.status=="ok" 的行，按 candidate 升序
            dataset_for_parent = "test"                         # 让父类 __init__ 的白名单校验通过；父类读到的 test 元数据随后不被使用
        super().__init__(env_id, dataset_for_parent, action_space, max_steps, override_metadata_path)
        self.dataset = dataset
    def _resolve_metadata_path(self):                           # train 的 Unmask 四个走 robomme_hard 包内 400 条
        if self.dataset == "train" and self.env_id in _HARD_TRAIN_OVERRIDE and self.override_metadata_path is None:
            return str(_PKG_METADATA / "train" / f"record_dataset_{self.env_id}_metadata.json")
        return super()._resolve_metadata_path()
    def get_episode_num(self):  return len(self._hard.rows) if self._hard else super().get_episode_num()
    def resolve_episode(self, episode): ...                     # hard：返回 (seed, tier, candidate)；info 里带 hard_candidate_index
    def make_env_for_episode(self, episode, **kw):              # hard：kwargs = 父类四项 runtime + seed + difficulty=tier
        ...                                                     #        + sampling_config=header["sampling_config"][env_id] + native_episode_spec=row["spec"]
    @classmethod
    def get_difficulty_list(cls): return list(_HARD_TIERS)
    @classmethod
    def from_v4_specs(cls, env_id, header, rows): ...           # 薄包装：允许任意路径的 jsonl（保留，仓库内无调用方）
```

- **`dataset_for_parent="test"` 的取舍**：父类 `__init__` 在 `_ALLOWED_DATASETS` 白名单外直接 `raise`，且它是官方原样不能改；子类先把白名单能过的值喂给父类，再把 `self.dataset` 改回档名。父类顺手读的 `test` 元数据不影响 hard 路径（`resolve_episode` 等全被覆写）。这是继承官方 builder 唯一的别扭之处，写进 README「实现说明」。
- **episode 编号**：`for episode in range(env_builder.get_episode_num())` 循环体不改，`episode` 是 `ok` 行按 `candidate` 升序的序号 0..2，原候选序号放 `info["hard_candidate_index"]`；这样递补后合作者跑到的就是真正生成成功的那一局（E-3 闭合点）。
- **`make_env_for_episode` 的 runtime 四项**：从 header `runtime` 取，并与父类拼出的四项逐字比对，不等 `raise`（`hard_specs` 的封套校验之一，现 `v4_specs.RUNTIME` 口径）。
- 录像器：hard 路径套 `robomme_hard` 的 `RobommeRecordWrapper`（`fail_safe_limit=5000`）。

`scripts/evaluation_hard.py`：复制 `evaluation.py`，只改 ①`from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder`；②`for tier in BenchmarkEnvBuilder.get_difficulty_list():` 套在 `for task in TASKS` 外，`dataset=tier`；③视频文件名加 `tier`。判定 `diff scripts/evaluation.py scripts/evaluation_hard.py | grep -c '^[<>]'` ≤ 12（第二轮 §5.4 上限不变）。

合作者视角（G4）：`pip install` 本仓库 → `python scripts/evaluation_hard.py`，或三行 `BenchmarkEnvBuilder("BinFill", dataset="xhard3")` → `make_env_for_episode(0)`。看得到的只有 `src/robomme_hard/env_metadata/xhard*/specs.jsonl`。

### 〇′.7 `scripts/parity/`：只做「与官方比」

#### 〇′.7.1 三条对拍

| 入口 | 比什么 | 现状 | 本轮 |
|---|---|---|---|
| `train_split_parity.py` | 官方源码树跑 S0 基线 144 局 vs 主仓代码同 seed 144 局，逐局 h5 sha | 已有，S0 基线 `artifacts/newtask-v6/v1/base` | 不动；`--official-root` 默认改 `scripts/parity/official` |
| `hard_parity.py`（V1′） | `robomme_hard` 跑原三档 144 局 vs S0 基线 | 阶段 0b 已落，`--env-package` 已有 | `--official-root` 默认改 vendor；`.official_tree` 校验改为读 `official/SOURCE.json` 的 `tree` |
| `hard_regression.py`（新） | xhard 四档：回注 reset 复现 + 正式局 h5 sha 复现 | 无 | §〇′.8 |

Q2 的「用同样的方式生成 easy medium hard 的 16×3×3」取 A 解读：`train_split_parity.py run --paths B` 本来就是用主仓代码（切到 `robomme_hard` 后即 hard 包）按官方 seed 生成原三档 16×3×3=144 局，再 `compare` 比 sha；不再另起「原三档也走抽签→封存→回注」的 B 路（多 144 reset + 144 rollout，用户未指定）。

#### 〇′.7.2 vendor 官方执行代码（E-10）

`scripts/parity/official/` 放官方 `scripts/data-generation/` 下四个文件（`generate_dataset.py` 563 行；它 `from validate_generated_dataset_contract import …`、`from write_generation_report import …`，后者又 `from compare_joint_actions import …`，四者缺一不可 import），加 `SOURCE.json`：

```json
{"url": "https://github.com/RoboMME/robomme_benchmark", "commit": "1fadc0ec…", "tree": "1d4c1369…",
 "path": "scripts/data-generation", "files": {"generate_dataset.py": "<sha256>", "...": "..."},
 "vendored_at": "2026-09-27", "note": "只作 train_split_worker 的 planner/_execute_tasks 来源；本仓库不改这四个文件"}
```

- 正本第 24 条：普通源码目录、无独立 `.git`、来源清单记 commit 与文件清单、升级时显式记新 commit；**本仓库不修改这四个文件**（要改就得按第 24 条另开分支，目前无此需求）。
- `train_split_runner.py` 的 `--official-root` 语义不变（把 `<root>/scripts/data-generation` 插 `sys.path`），vendor 目录按 `scripts/parity/official/scripts/data-generation/` 布局放置以免改 runner；`SOURCE.json` 放 `scripts/parity/official/` 顶层。
- `artifacts/train-parity/local-smoke-01/official-src/` 整棵树保留（S0 基线的 `.official_tree` 证据链仍指向它），但生产与对拍默认不再依赖它；阶段 0 用 `sha256sum` 逐文件证明 vendor 四文件与该树同名文件相同，判定行 `VENDOR_SAME=PASS files=4`。

### 〇′.8 回归闸门总表与预算

| 判定行 | 查什么 / 怎么查 | 过了说明什么 | reset | rollout |
|---|---|---|---|---|
| `UPSTREAM_BYTES=PASS commit=… files=… diff=0 borrowed=…` | §〇′.3 守卫脚本 | G1 | 0 | 0 |
| `VENDOR_SAME=PASS files=4` | vendor 四文件 sha == 隔离树同名文件 | 执行代码来源未变 | 0 | 0 |
| `ABS_IMPORT=PASS … stray=0` | §〇′.2.2 AST 扫描 | 无静默回头用官方旧逻辑 | 0 | 0 |
| `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` | 三种导入顺序（只 hard；官方→hard；hard→官方）各起一进程，`REGISTERED_ENVS[uid].cls.__module__` 全部 `robomme_hard.` 开头 | G5 | 0 | 0 |
| `SPECS_IDENTITY=PASS tiers=4 rows=550 selected=165` | 包内四份 jsonl 迁移后 `identity_sha256`（按新收窄口径重算）与由 `v6-02` 同口径重算值相等；`spec_sha256` 逐行相等 | 分发的规格就是 S4 生成用的那份 | 0 | 0 |
| `EVAL_PY_UPSTREAM=PASS ENTRIES=5` | `cmp` 三脚本与官方；`ls -1 scripts/*.py \| wc -l` = 5 | 冻结项未破 | 0 | 0 |
| `EVAL_HARD_DIFF=PASS lines=<n≤12>` | §〇′.6 | 接口只差 import 与循环 | 0 | 0 |
| `FREEZE_DRYRUN_EQUIV=PASS` | `freeze_specs.py --dry-run` 打印的 draw／freeze 参数与 `v5_generation.plan_pipeline` 输出逐项相等 | 两阶段入口没有改抽签口径 | 0 | 0 |
| `FREEZE_ONLY_JSONL=PASS files_written=1` | 单任务单档 1 候选 smoke（`--tasks BinFill --candidates-per-env 1`），运行后工作区与 `artifacts/` 无新文件 | G6 上半 | 1 | 0 |
| `ROLLBACK_WRITE=PASS spec_hash_unchanged=1` | 对上一行的 smoke jsonl 跑 `generate_h5.py`，回写后 `identity_sha256` 不变、`rollout` 块齐全 | G6 下半 | 0 | 1 |
| `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144` | V1′（`hard_parity.py run --env-package robomme_hard`，1 条冒烟 + 143 条，30 分钟无进展／4 小时硬上限） | G2 | 0 | 144（**已授权**，第二轮 D 项） |
| `HARD_RESET_REPLAY=PASS resets=55 mismatch=0` | **xhard 侧①**：每档每任务取 `candidate` 最小的 `ok` 行 1 条（xhard1/2/3 各 13 任务、xhard4 16 任务 = 55），`gym.make(native_episode_spec=…)` + `reset()`，导出 `_spec.to_dict()` 与冻结 `spec` 逐字段比（现 `v4_eval._binding` 的 `mismatch/unused` 口径） | 回注通道在新包下逐值一致 | **55** | 0 |
| `HARD_ROLLOUT_SHA=PASS compared=16 sha_equal=16` | **xhard 侧②**：16 任务各 1 局，档位轮换（任务序号 i 取 `xhard{(i mod 4)+1}`，xhard4-only 的三个任务固定 xhard4），h5 sha 与 `final-delivery.json` 所记 S4 交付 sha 比 | 新包在 xhard 下产物逐位同 S4 | 0 | **16** |
| `HARD_EVAL_SMOKE=PASS` | `evaluation_hard.py` 限 1 任务 1 档 1 局跑通并落视频 | 合作者入口可用 | 0 | 1 |

**预算合计（P3 一次性申请）**：reset 56 次（55 + 1 smoke）、rollout 162 次（144 已授权 + 16 + 1 + 1）。本轮新增待授权：**reset 56、rollout 18**。用户 Q8/Q10 已表示「其他都同意」，实施前在阶段 4 起跑那一条回复里把这两个数字再复述一次即视为执行授权；数字若因 `final-delivery.json` 实际可比局数而缩小，只减不增。FAIL 时不自行放宽、不重试挑成功，记证据链交用户。

### 〇′.9 阶段表（取代第二轮附录 A §七的阶段 2～5）

| 阶段 | 内容 | 判据 | 改 `src/robomme` | commit |
|---|---|---|---|---|
| 0 只读准备 | ①`git fetch` 官方 `1fadc0ec`，`git rev-parse ^{tree}` 与 `1d4c1369` 对照并记录；②生成 `UPSTREAM.json`（`robomme_files` 以官方树为准、`borrowed` 按 §〇′.2.1 清单）；③vendor 四文件 + `SOURCE.json`；④`register_env` 重复语义用一行脚本复核（本节已按源码写死，实测只为留证）；⑤绝对 import 全量扫描出清单 | `VENDOR_SAME`、扫描清单落 `docs/validation/newtask-v6/hard-split/stage0.md` | 否 | 12.205 |
| 1 建 `robomme_hard` | 复制 16 环境（改 `override=True`）、17 个 utils、`RecordWrapper.py`、`OraclePlanner…`；写 15 个 shim、`__init__.py` 守卫、`hard_builder.py`、`hard_specs.py`、`env_record_wrapper/__init__.py`；迁四份 jsonl（`v6-02` → 新 schema，重算收窄口径的 `identity_sha256`，两段指纹）；`pyproject.toml` 加包 | `REGISTRY_OWNER`、`ABS_IMPORT`、`SPECS_IDENTITY`；`python -c` 单局 `make_env_for_episode` 冒烟（1 rollout，计入 `HARD_EVAL_SMOKE`） | 否 | 12.206 |
| 2 `scripts/` 重组 | 建 `injection-dev/` 五个内部模块 + 两个入口 + `site/`；`parity/` 按 §〇′.4 去留；`upstream_guard.py`、`hard_regression.py`、`evaluation_hard.py`；`train_split_worker.py` 加 `ROBOMME_ENV_PACKAGE` 分支；`tests/` 的 `from robomme.` 机械改 `robomme_hard.`（只保证可收集） | `FREEZE_DRYRUN_EQUIV`、`FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE`、`EVAL_PY_UPSTREAM`、`EVAL_HARD_DIFF`、`--collect-only` 错误 0 | 否 | 12.207 |
| 3 回退 `robomme` | 用官方树覆盖 `src/robomme/**`（含 `env_metadata/`），`git rm` 9 个新增 utils 与 4 份 400 条 train 元数据（换回 100 条） | `UPSTREAM_BYTES=PASS`；阶段 1、2 的判定行全部重跑仍 PASS | **是（P2：逐文件清单交用户批准）** | 12.208 |
| 4 回归 | V1′ 144 + xhard 侧 55 reset / 17 rollout（§〇′.8 预算） | `NATIVE_REGRESSION_HARD`、`HARD_RESET_REPLAY`、`HARD_ROLLOUT_SHA`、`HARD_EVAL_SMOKE` | 否 | 12.209（起跑前 HEAD 冻结，结果以子节追加） |
| 5 留档 | `robomme_hard/README.md`（§〇′.11）、`scripts/README.md` 与 `parity/README.md` 重写、`docs/validation/newtask-v6/hard-split/` 汇总全部判定行、`AGENTS.md` P1 改五入口与本节路径、`CLAUDE.md` 核实清单 | `git diff --check`；链接可达 | 否 | 12.210 |

阶段 3 放在 2 之后、4 之前：先让 `robomme_hard` 在 `robomme` 还带改动时独立跑通（此时借用的文件与官方相同，`UPSTREAM.json` 的 `borrowed` sha 已能命中），再回退 `robomme`，最后对拍——这样阶段 3 失败时可以只回滚一个 commit。

### 〇′.10 风险登记与盲区

| # | 风险 | 处置 |
|---|---|---|
| 1 | shim 借用触发官方 16 环境注册 → 日志里 16 条 `Override registered env` 警告噪声 | 接受；`robomme_hard/__init__.py` 在自家注册阶段临时把 `mani_skill` logger 提到 ERROR 再恢复，只压这一段；不压 `REGISTRY_OWNER` 断言 |
| 2 | 官方 `main` 前进后，借用文件变化悄悄改了 xhard 行为 | `UPSTREAM.json` 钉 commit，守卫脚本 FAIL 即停；升级官方 commit 是显式动作，须重跑 §〇′.8 全部闸门 |
| 3 | 父类 `__init__` 白名单绕行（`dataset_for_parent="test"`）在官方 builder 未来改签名时断裂 | 子类只调用父类公开签名；官方变更属风险 2 的升级流程 |
| 4 | `identity_sha256` 收窄后旧 `v6-02` 文件的值不再直接可比 | `SPECS_IDENTITY` 以「同口径重算」为判据，并把旧值一并写进 header `record.legacy_identity_sha256` 留痕 |
| 5 | `injection-dev` 连字符目录名与 `-m` 不兼容 | §〇′.5.1 已定：路径直跑；若出现 import 混乱再请示改名 |
| 6 | 回写与并发：两个 `generate_h5.py` 同时对同一 jsonl 回写 | 第 5 步的「读前哈希 == 写前哈希」只能挡住串行改动；同一 jsonl 同时只允许一个第二阶段进程，写进 README 红线，并在 `--output` 下放 `.lock` 文件（`O_EXCL`） |
| 7 | `tests/` 只保证可收集，语义失效的测试会给出假 PASS／假 FAIL | E-11 用户裁决；留档里列出被机械替换的 45 个文件，标「未验证语义」 |

盲区（诚实清单）：①官方 `episode_config_resolver.py` 是否已有 `get_difficulty_list`／`get_task_list` 之外的类方法被 `evaluation.py` 依赖，阶段 0 读官方树核实；②`MultiStepDemonstrationWrapper` 借用后其内部 `from ..robomme_env.utils import planner_denseStep` 解析到**官方**的 utils（父包是 `robomme`），与 `robomme_hard` 环境同进程使用时是否有状态耦合，阶段 1 冒烟观察；③`final-delivery.json` 里可比的 h5 sha 是否覆盖全部 16 任务，阶段 4 起跑前核，不足则 `HARD_ROLLOUT_SHA` 的 `compared` 按实际减少并写明。

### 〇′.11 `src/robomme_hard/README.md` 必含内容

①一句话：hard = 四档 `xhard1<xhard2<xhard3<xhard4`，原三档在本包下与官方逐位相同（附 V1′ 判定行原文）；②四档定稿表（从 `0925-newtask-release-v6-plan.md` 第一部分 §三逐字搬）；③「哪些是自己的、哪些借官方的」表：由 `upstream_guard.py --manifest-md` 生成（复制／借用／子类／新增四类，逐文件），内联结果与生成命令；④机制：`sampling_config` 两块结构、`SpecRecorder` 导出／回注、jsonl 封套（`spec` 块定死、`rollout` 块可回写）、seed 偏移公式、注册表归属（`override=True` + 守卫）；⑤使用：`evaluation_hard.py` 三行示例、`override_metadata_path` 用法、两阶段生产命令（注明不随包分发）；⑥红线：同进程导入 `robomme_hard` 后 16 个 id 归它；同一 jsonl 同时只许一个回写进程；xhard 不受 1301 步限制；`fail_safe_limit=5000`；⑦实现说明：`dataset_for_parent="test"` 绕行的原因。

### 〇′.12 红线（本轮追加，编号接第二部分 §〇 的 R1～R7）

- R8 `src/robomme/**` 从阶段 3 起是官方原样，**本仓库不再往里放任何自有文件**（含 `UPSTREAM.json`、README 补充、`__pycache__` 之外的一切）；需要的说明一律放 `robomme_hard/` 或 `docs/`。
- R9 `scripts/parity/official/` 四文件不改；`robomme_hard` 的 shim 不含逻辑（守卫脚本按 ≤ 3 行非注释行检查）。
- R10 `identity_sha256` 覆盖范围（§〇′.5.2）一经阶段 1 落地不再变更；变更即换 `schema` 版本号并重跑 `SPECS_IDENTITY`。
- R11 第二阶段回写只改 `selected` 与 `rollout` 两个键；`--force` 覆盖 jsonl 起跑前 `ls -ld` 并在回复里复述目标路径（正本第 14 条）。
- R12 阶段 4 的 reset／rollout 计数按 §〇′.8 表逐项记入留档，冒烟与重跑都计入；超出表内数字先停再补充授权（P3）。

## 一、env make 的接口：外层多传什么、内部多传什么（第二轮内容，已被 §〇′ 取代，保留原文）

分两层看：外层是 `scripts/evaluation.py` 里用户写的那个 `BenchmarkEnvBuilder(...)` 调用；内部是 builder 在 `make_env_for_episode` 里拼给 `gym.make` 的 kwargs。

### 1.1 外层：`evaluation.py` 的调用只改一个参数的取值，不加新参数

上游 `evaluation.py` 原样：

```python
env_builder = BenchmarkEnvBuilder(
    env_id=task,
    dataset="test",
    action_space="joint_angle",
    max_steps=1300,
)
```

`evaluation_hard.py` 里对应写法：

```python
env_builder = BenchmarkEnvBuilder(
    env_id=task,
    dataset=tier,            # 唯一变化：取值从 "test" 变成 "xhard1" / "xhard2" / "xhard3" / "xhard4"
    action_space="joint_angle",
    max_steps=1300,
)
```

| 参数 | `evaluation.py` | `evaluation_hard.py` | 说明 |
|---|---|---|---|
| `env_id` | 任务名 | 任务名 | 不变 |
| `dataset` | `"test"` | `"xhard1"`～`"xhard4"` | **唯一变化**。原值域 `{train,test,val}` 扩为七个 |
| `action_space` | `"joint_angle"` | `"joint_angle"` | 不变 |
| `gui_render` | 默认 `False` | 默认 `False` | 不变 |
| `override_metadata_path` | 默认 `None` | 默认 `None` | 不变；xhard 档下若传，解释为「含 `<tier>/specs.jsonl` 的目录」 |
| `max_steps` | `1300` | `1300`（值由用户定，xhard 不受 1301 限制，默认仍传 1300） | 不变 |

**外层不多传任何新参数。** 后面用到的 `get_task_list()`、`get_episode_num()`、`make_env_for_episode(episode)` 三个方法签名与返回类型也不变。新增的只有一个类方法 `get_difficulty_list()`，`evaluation_hard.py` 用它做外层循环；三个无梯度任务（MoveCube / InsertPeg / StopCube）在 xhard1～3 下 `get_episode_num()` 返回 0，循环体自然跳过。

### 1.1.1 最小用法：只改 `dataset` 一个字符串，其余逐字不动（用户 2026-09-27 确认口径）

用户原话：「`dataset="test"` 能否只改这里 改为 xhard1 xhard2 xhard3 xhard4 其他都正常？」答：可以。把 `scripts/evaluation.py` 原样复制，只做两处：

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder   # ① import 指向新包（旧包不认 xhard，会 ValueError）
...
        dataset="xhard3",          # ② 唯一要改的取值；换 xhard1/2/4 各跑一次即四档
```

循环体、`get_task_list()`、`get_episode_num()`、`make_env_for_episode(episode)`、`reset()`/`step()`、`max_steps=1300`、视频落盘、成功率计算全部原样。各处在 xhard 档下的行为：

| 位置 | 行为 |
|---|---|
| `TASKS = get_task_list()` | 仍 16 任务固定序 |
| `get_episode_num()` | 13 个有梯度任务返回 3；MoveCube / InsertPeg / StopCube 在 xhard1～3 返回 0（`range(0)` 自然跳过，不需加 `if`），xhard4 返回 3 |
| `make_env_for_episode(0/1/2)` | 起该档三条正式规格；候选序号 0/3/6 在 builder 内重编为 0..2 |
| `info["task_goal"]`、`info["status"]`、`obs` 形状 | 与原三档相同 |

因此 `for tier in get_difficulty_list()` 那层外循环只是为了一次跑完四档，**不是必需**；H4「改一行 import 就能用」在这条最小用法下成立。唯一副作用：四档同任务同 episode 的视频文件名相同，分四次跑要各自换输出目录或在文件名里加档名。

### 1.2 内部：builder 按 `dataset` 取值分两条路，拼给 `gym.make` 的 kwargs 多三项

`make_env_for_episode(episode)` 内部最终调 `gym.make(self.env_id, **env_kwargs)`。两条路的 `env_kwargs`：

| kwarg | `dataset="test"`（上游原样，`robomme` 与 `robomme_hard` 相同） | `dataset="xhardN"`（只有 `robomme_hard`） | 值从哪来 |
|---|---|---|---|
| `obs_mode="rgb+depth+segmentation"` | 传 | 传 | builder 写死 |
| `control_mode="pd_joint_pos"` | 传 | 传 | builder 写死 |
| `render_mode="rgb_array"` | 传 | 传 | builder 按 `gui_render` 定 |
| `reward_mode="dense"` | 传 | 传 | builder 写死 |
| `seed` | 传 | 传 | test：包内 `env_metadata/test/record_dataset_<task>_metadata.json` 该 episode 的 `seed`；xhard：包内 `env_metadata/<tier>/specs.jsonl` 该行的 `seed` |
| `difficulty` | 传，`easy/medium/hard` | 传，`xhardN` | 同上两个文件 |
| `sampling_config` | **不传** | **多传**：header 里该任务那一段（16 任务的 decision/native 块） | `specs.jsonl` 的 header |
| `native_episode_spec` | **不传** | **多传**：该行的 `spec`，让 `SpecRecorder` 进回注模式，每个取值点用冻结值、原抽样照常发生只作核验 | `specs.jsonl` 的行 |
| `robomme_failure_recovery` / `robomme_failure_recovery_mode` | **不传** | 条件传：header 的 `recovery_rule` 把该 episode 划进 z 或 xy 段时才传；V6 正式规格 `recovery_rule` 为空，实际**不传** | `specs.jsonl` 的 header |

所以内部多传的就是 `sampling_config`、`native_episode_spec` 两项必传，`robomme_failure_recovery` 一项条件传。`sampling_config` 严格说可以省（不传时环境用类里的 `NATIVE_SAMPLING` 默认值，V6 快照正是从源码导出的同一份），传它是为了让 header 的 `sampling_config_sha256` 校验能挡住「包内源码与分发规格对不上」。

`gym.make` 之后的包装层（`DemonstrationWrapper` 及按 `action_space` 选的 `Endeffector` / `MultiStep` / `OraclePlanner` wrapper）两条路完全相同，模型看到的 `obs` / `info["task_goal"]` / `step()` 五元组形状一致。

### 1.3 builder 内部要改的三处

| 锚点 | 现状 | 改成 |
|---|---|---|
| `episode_config_resolver.py::_ALLOWED_DATASETS` | `{"train","test","val"}` | 并入 `NEWVALUE_DIFFICULTIES` 四档 |
| `BenchmarkEnvBuilder.__init__` | 只走 `_resolve_metadata_path` → `load_episode_metadata` | `dataset` 是 xhard 值时改走 `hard_specs.load_specs(包内 env_metadata/<tier>/specs.jsonl)`，把 header 该任务段与行装进 `self._hard`（即现 `from_v4_specs` 装 `self._v4` 的那套结构） |
| `BenchmarkEnvBuilder.get_difficulty_list` | 不存在 | 新增类方法，返回四档列表 |

`resolve_episode` / `get_episode_num` / `make_env_for_episode` 现在已经有 `self._v4` 分支（`from_v4_specs` 路径在用），只需把 `_v4` 改名 `_hard` 并让 `__init__` 也能填它；`from_v4_specs` 保留为薄包装以免打断现有 `scripts/eval/v4_eval.py`。episode 编号：xhard 行的候选序号是 0/3/6，builder 内存里重编为 0..2 让 `for episode in range(episode_count)` 循环体不改，原候选序号放 `info["hard_candidate_index"]`；规格行与 `identity_sha256` 不动。

## 二、文件级清单：`src/robomme_hard` 从哪来、哪些不动、哪些要加 （第二轮内容，已被 §〇′.2 取代，保留原文）

`src/robomme_hard/` = 当前 `src/robomme/` 整包复制（D-2 已推荐 copy）。下面按「相对上游 `main` 是否相同」分四组；「继承」指从当前 `src/robomme` 原样复制进 `robomme_hard` 后一个字不改。

### 2.1 原样继承（与上游逐字节相同，28 个 .py + 44 个 json）

| 位置 | 文件 | 备注 |
|---|---|---|
| 包顶层 | `__init__.py`、`logging_utils.py` | — |
| `robomme_env/` | `__init__.py` | 16 个 `@register_env` 的登记处 |
| `env_record_wrapper/` | `__init__.py`、`DemonstrationWrapper.py`、`EndeffectorDemonstrationWrapper.py`、`MultiStepDemonstrationWrapper.py`、`FailAwareWrapper.py`、`episode_dataset_resolver.py` | — |
| `env_record_wrapper/` | `OraclePlannerDemonstrationWrapper.py` | ⚠ 内容同上游，但含 `from robomme.…` 绝对 import，复制后须改包名 |
| `robomme_env/utils/` | `__init__.py`、`adjacent.py`、`choice_action_mapping.py`、`constant.py`、`obschange.py`、`oracle_action_matcher.py`、`planner_denseStep.py`、`planner_fail_safe.py`、`planner-ref.py`、`reset_panda.py`、`rpy_util.py`、`save_reset_video.py`、`SceneGenerationError.py`、`statechange.py`、`task4recovery.py` | — |
| `robomme_env/utils/` | `generate_sample_action.py`、`subgoal_evaluate_func.py`、`vqa_options copy.py` | ⚠ 同上，含绝对 import，复制后须改包名 |
| `env_metadata/` | `test/` 16 份、`val/` 16 份、`train/` 12 份 | 原三档身份 |

### 2.2 已被 V3～V6 改过（与上游不同，26 个 .py + 4 个 json）——复制进 `robomme_hard`，`robomme` 侧回上游

| 位置 | 文件 | 改动规模（相对上游） | 复制后还要做什么 |
|---|---|---|---|
| `robomme_env/` | 16 个环境文件 `BinFill.py` … `VideoUnmaskSwap.py` | 每个 +200～+1100 行：`sampling_config` / `episode_spec` 接入、xhard 分支 | 不改 |
| `env_record_wrapper/` | `RecordWrapper.py` | +7 行：`fail_safe_limit` 2000→5000（V4 用户授权的唯一解冻） | 改绝对 import |
| `env_record_wrapper/` | `episode_config_resolver.py` | +79 行：`from_v4_specs` / `v4_episodes` / `_v4_kwargs` | **要加东西**：`_ALLOWED_DATASETS` 并入四档、`__init__` 的 `dataset` 分支读包内规格、`get_difficulty_list()`（§一） |
| `robomme_env/utils/` | `difficulty.py`、`object_generation.py`、`route.py`、`segmentation_utils.py`、`subgoal_language.py`、`task_goal.py` | 各 +20～+340 行 | 不改 |
| `robomme_env/utils/` | `subgoal_planner_func.py`、`vqa_options.py` | +104 / +21 行 | 改绝对 import |
| `env_metadata/train/` | `ButtonUnmask`、`ButtonUnmaskSwap`、`VideoUnmask`、`VideoUnmaskSwap` 四份 | 100 条→400 条 | 留在 `robomme_hard`（D-3） |

### 2.3 fork 新增（上游没有，9 个 .py）——复制进 `robomme_hard`，`robomme` 侧删除

`robomme_env/utils/`：`bin_collision.py`、`episode_spec.py`、`sampling_config.py`、`swap_uniform.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py`、`unmask_swap_xhard.py`、`xhard.py`、`xhard_home_site.py`。复制后不改。

### 2.4 `robomme_hard` 相对当前 `src/robomme` 还要**新增**的（5 项）

| 文件 | 内容 | 来源 |
|---|---|---|
| `__init__.py`（改写） | 同进程已 import `robomme.robomme_env` 时 `raise ImportError`（ManiSkill 注册表按 env_id 唯一，两包不能共存） | 新写 |
| `env_record_wrapper/hard_specs.py` | `load_specs()` 及其纯函数依赖（`canonical_json`、`digest`、`identity_sha256`、`seed_rule_for`、`HEADER_KEYS`） | 从 `scripts/parity/v4_specs.py` 下沉只读部分；`draw`/`freeze` 不搬 |
| `env_metadata/xhard{1,2,3,4}/specs.jsonl` | 四档冻结规格 | `cp scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（现行 v6-02，非方案初稿的 v6-01） |
| `README.md` | 四档定义、改动清单、用法 | 新写，改动清单由 `scripts/parity/hard_pkg_manifest.py` 生成 |
| `pyproject.toml` | `packages = ["src/robomme", "src/robomme_hard"]` | 一行 |

绝对 import 共 7 个文件要改（2.1 的 4 个 + 2.2 的 3 个）：`from robomme.` → `from robomme_hard.`，或改相对 import。这是拆包时唯一容易漏的洞，漏一处就静默回头用旧包。

## 三、三个脚本阶段：env make 怎么传 （第二轮内容，已被 §〇′.5 取代，保留原文）

三阶段的入口都在 `scripts/`，每阶段一句话说它调不调 `gym.make`、传什么。

```
阶段 1  生成 json    train_split_config.py extract --release newtask-v6
        ──▶ scripts/configs/newtask-v6/sampling_config.json        （不起环境）
阶段 2  生成规格与轨迹
   2a   v4_specs draw --difficulty <tier> --seed-profile v6           gym.make + reset，只抽签不 step
        ──▶ drafts.jsonl
   2b   v4_specs freeze                                              纯 CPU，不起环境
        ──▶ scripts/configs/newtask-v6/<run>/<tier>/specs.jsonl
   2c   v4_rollout run --specs <tier>/specs.jsonl                    gym.make + RecordWrapper + planner
        ──▶ h5 / mp4
阶段 3  评估          evaluation_hard.py（或现有 scripts/eval/v4_eval.py）  BenchmarkEnvBuilder → gym.make
```

| 阶段 | 入口 | 起环境的代码位置 | `gym.make` 收到的 kwargs | 拆包后要改的 |
|---|---|---|---|---|
| 1 生成 json | `scripts/parity/train_split_config.py::extract_task` | **不调 `gym.make`**。`importlib.import_module("robomme.robomme_env.<Task>")` 读类属性 `NATIVE_SAMPLING` / decision 块，写成 json | 无 | import 串改 `robomme_hard` |
| 2a 抽签 | `scripts/parity/v4_specs.py::_draw_one` | `gym.make(task, sampling_config=<json 该任务段>, **env_kwargs(seed, episode, difficulty))` → `env.reset()` → `env.unwrapped._spec.to_dict()` 导出规格 | 四项 runtime + `seed` + `difficulty=xhardN` + `sampling_config`（+ recovery，V6 为空） | `from robomme.` → `robomme_hard` |
| 2b 冻结 | `scripts/parity/v4_specs.py::cmd_freeze` | 不起环境；校验 header 与源码指纹后写 `specs.jsonl` | 无 | `load_specs` 改为薄包装调 `robomme_hard.…hard_specs.load_specs` |
| 2c 实跑 | `scripts/parity/v4_rollout.py` → `train_split_worker.py::run_one` | `gym.make(job.task, **kwargs)` 再套 `RobommeRecordWrapper` 与 planner | 四项 runtime + `seed` + `difficulty` + `sampling_config` + `native_episode_spec`（+ recovery） | import 改包名 |
| 3 评估（现状） | `scripts/eval/v4_eval.py` | `load_specs` → `BenchmarkEnvBuilder.from_v4_specs(task, header, rows)` → `make_env_for_episode(ep)` | 与 2c 相同（builder 内 `_v4_kwargs` 拼出） | import 改包名；`from_v4_specs` 保留为薄包装 |
| 3 评估（方案后） | `scripts/evaluation_hard.py` | `BenchmarkEnvBuilder(env_id=task, dataset="xhardN")` → `make_env_for_episode(ep)`，builder 自己读包内 `specs.jsonl` | 与 2c 相同 | 新增文件（与 `evaluation.py` diff ≤ 12 行，见第二部分 §5.4） |

三点结论：

1. **2a、2c、3 传进 `gym.make` 的 kwargs 集合是同一套**，差别只在 2a 没有 `native_episode_spec`（它正是要导出这个），2c/3 有。这就是回注能逐位复现的原因：抽签时导出的规格，实跑和评估原样喂回去。
2. **阶段 1 和 2b 不起环境**，只 import 包读属性或算散列，所以对 `robomme_hard` 的依赖只是 import 串。
3. **阶段 3 现状与方案后的唯一区别是「谁读 `specs.jsonl`」**：现在是脚本读了再喂 builder（`from_v4_specs`），方案后 builder 按 `dataset` 档名自己读包内规格。合作者拿到包后只需要 `dataset="xhard3"`，不需要知道 `scripts/parity` 存在。

原三档在 `robomme_hard` 下走的是与上游相同的 metadata 路径（`dataset="test"`），kwargs 只有四项 runtime + `seed` + `difficulty`，与 `robomme` 逐字相同；这条路的逐位一致由第二部分 §2.2 的 V1′ 对拍保证。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 **（2026-09-27 改写）S3 与审查修复 G1 均已通过，D-4 满足；`src/robomme/` 的整体回退仍只在阶段 5、且排在 V1′ PASS 之后**；阶段 0～4 只新增文件或改 `scripts/`、`tests/`、`pyproject.toml`，阶段 0b 的删除按附录 B 勾选清单。
- R2 `src/robomme/` 的目标字节 = 上游 `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`；取法只允许 `git fetch https://github.com/RoboMME/robomme_benchmark.git main` 后 `git checkout FETCH_HEAD -- src/robomme`（不合并、不 rebase）。
- R3 `robomme_hard` 内零 `robomme.` 绝对 import；两包同进程互斥由 `robomme_hard/__init__.py` 负责，`robomme` 不改。
- R4 `specs.jsonl` 行内容与 `identity_sha256` 不动；builder 侧 episode 重编号只在内存。
- R5 三脚本 `evaluation.py` / `run_example.py` / `dataset_replay.py` 继续逐字节同上游；`evaluation_hard.py` 只允许 §5.4 的 diff。
- R6 V1′ 144 次轨迹尝试是本方案唯一的生成预算（P3：单 worker >10 须授权，阶段 1 一次列齐）；不加 reset 对拍、不加 rollout。
- R7 commit 只 add 本阶段文件。**当前在途改动（2026-09-27，属其他会话）一律不碰、不读、不删**：`M scripts/parity/v6_site.html`、`M scripts/parity/v6_site.py`、`?? logs/`、`?? scripts/configs/newtask-v6/smvla-smoke-0927/`、`?? scripts/parity/v6_gt_lengths.{py,json}`；以及 `artifacts/newtask-v6/smvla-0927{,-more,-fill,-smoke}`（约 2 TB，`logs/gen-*.sh` 的产物，账本无记录）与 tmux 会话 `smvla-site-8060`、`corlvis-site`。实施时以当时 `git status --short` 为准重列。
- R8 长期文档禁行号引用；本文件锚点全部用 `文件::符号`。

## 一、逐文件改动清单 （第二轮内容，已被 §〇′.2／§〇′.4 取代，保留原文）

### 1.1 `src/robomme_hard/`（阶段 2）

| 文件 | 锚点 | 改动 |
|---|---|---|
| `__init__.py` | 模块顶部 | `import sys; if "robomme.robomme_env" in sys.modules: raise ImportError(...)`；其余空 |
| `robomme_env/utils/subgoal_planner_func.py` | 顶部 `from robomme.robomme_env import *`、`from robomme.robomme_env.utils import *` | 改 `from robomme_hard…`（保持星号，不改语义） |
| `robomme_env/utils/subgoal_evaluate_func.py` | `from robomme.robomme_env.utils import *` | 同上 |
| `robomme_env/utils/vqa_options.py`、`vqa_options copy.py` | `from robomme.robomme_env.utils.subgoal_planner_func import (` | 同上（`copy.py` 是上游遗留死文件，随包复制、不删） |
| `robomme_env/utils/generate_sample_action.py` | 函数内 `from robomme.robomme_env.utils.rpy_util import …` | 同上 |
| `env_record_wrapper/OraclePlannerDemonstrationWrapper.py` | `from robomme.robomme_env.utils.vqa_options import get_vqa_options` | 改相对 `from ..robomme_env.utils.vqa_options import …` |
| `env_record_wrapper/RecordWrapper.py` | `_write_h5` 内局部 `from robomme.robomme_env.utils.vqa_options import get_vqa_options` | 同上；`fail_safe_limit = 5000` 保留 |
| `env_record_wrapper/episode_config_resolver.py` | `BenchmarkEnvBuilder.__init__`、`_ALLOWED_DATASETS`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode`、`from_v4_specs`、`v4_episodes`、`_v4_kwargs` | 按 §5.2：`_v4` 改名 `_hard`；`_ALLOWED_DATASETS` 并入四档；新增 `_resolve_specs_path()`、`get_difficulty_list()`、`hard_episodes()`；`from_v4_specs` 保留为包装 |
| `env_record_wrapper/hard_specs.py` | 新 | 从 `scripts/parity/v4_specs.py` 搬 `HEADER_KEYS`、`canonical_json`、`digest`、`identity_sha256`、`seed_rule_for`、`_known_seed_rule`、`load_specs`；`source_fingerprint` 不符改 `warnings.warn` |
| `env_record_wrapper/__init__.py` | 导出表 | 增 `hard_specs` |
| `env_metadata/xhard{1..4}/specs.jsonl` | 新 | `cp scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（现行 v6-02，2026-09-27 更正）；打包前按 §2.3 重算 `source_fingerprint` |
| `README.md` | 新 | §5.5 |

### 1.2 `scripts/`、`tests/`（阶段 3）

- 机械替换：`grep -rl "from robomme\.\|import robomme\b" scripts tests --include=*.py`（实测 14 + 45 文件）→ `robomme_hard`；**排除** `scripts/evaluation.py`、`run_example.py`、`dataset_replay.py`。
- `scripts/parity/v4_specs.py::load_specs` 改为 `from robomme_hard.env_record_wrapper.hard_specs import load_specs as _load; def load_specs(path): return _load(path)`；`draw`/`freeze` 不动。
- `scripts/parity/hard_pkg_manifest.py`（新，只读）：对 `src/robomme` 与 `src/robomme_hard` 逐文件 `sha256`/行数 diff，输出 Markdown 表 + `HARD_MANIFEST=PASS same=<n> diff=<m> new=<k>`。
- `scripts/evaluation_hard.py`：§5.4。
- `tests/lightweight/test_hard_pkg_isolation.py`（新）：AST 扫描零绝对引用；子进程验证双导入 `ImportError`；`specs.jsonl` 身份相等；`evaluation_hard.py` diff 行数 ≤ 12。

### 1.3 `src/robomme/`（阶段 5，P2）

```bash
git fetch https://github.com/RoboMME/robomme_benchmark.git main          # 只写 .git/FETCH_HEAD
git rev-parse FETCH_HEAD                                                  # 期望 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9
git rm -q src/robomme/robomme_env/utils/{bin_collision,episode_spec,sampling_config,swap_uniform,unmask_distractor_sampler,unmask_distractors,unmask_swap_xhard,xhard,xhard_home_site}.py
git checkout FETCH_HEAD -- src/robomme
git diff --stat FETCH_HEAD HEAD -- src/robomme | tail -1                  # 期望空 → UPSTREAM_BYTES=PASS
```

`pyproject.toml` 的 `pebble` 行保留（生成链路要用），只改 `packages`。

## 二、对拍闸门总表与 runbook （第二轮内容，闸门以 §〇′.8 为准，V1′ 命令仍有效）

### 2.1 上游快照

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
git fetch https://github.com/RoboMME/robomme_benchmark.git main && git rev-parse FETCH_HEAD
git diff --stat FETCH_HEAD HEAD -- src/robomme scripts/evaluation.py scripts/run_example.py scripts/dataset_replay.py pyproject.toml
```

2026-09-26 现状（scratchpad 浅克隆 `cmp` 实测）：`same=31 diff=26 new=9`，`env_metadata` 4 份 train 不同，`pyproject.toml` 差 `pebble` 一行，三脚本相同。

### 2.2 V1′（阶段 4）——由新入口 `scripts/parity/hard_parity.py` 承担

用户 2026-09-27 原话：「robomme_hard 重跑 144 局与 S0 基线比 sha 这个是要保留的！并且需要wrap up成新的 …/scripts/parity负责对拍」。

- **来源**：`artifacts/newtask-v6/v6-s3-20260926-01/run_s3.py`（225 行）的逻辑下沉——①先 1 条冒烟（`BinFill/0`）再剩余 143 条，失败不补跑；②逐局 H5 校验：身份目录集合、文件名 `<task>_ep<ep>_seed<seed>.h5`、`setup/seed`、`setup/difficulty`、timestep 连续、末帧 `info/is_completed` 严格 `True`；③子进程独立进程组，30 分钟无日志/文件进展或 4 小时硬上限即停；④调 `train_split_parity.py compare` 出 `h5_pairs.jsonl` 与 `summary.json`。**不新增任何抽样或 reset**。
- **CLI**：`uv run --no-sync python -m scripts.parity.hard_parity run --env-package robomme_hard --manifest scripts/configs/newtask-v3/subset_manifest.json --base artifacts/newtask-v6/v1/base --official-root artifacts/train-parity/local-smoke-01/official-src --output artifacts/newtask-v6/v1-hard --workers 1 --gpus 0`；`--env-package` 决定子进程里 `train_split_worker` import 的包名（通过环境变量 `ROBOMME_ENV_PACKAGE` 传入 worker，worker 侧按该变量选择 import；这是阶段 3 切换调用方时对 `train_split_worker.py` 的唯一非机械改动）；`--dry-run` 只打印将执行的命令。
- **判定行**：`NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144 field_mismatch=0 env_package=robomme_hard base=<sha256 of run_config>`；H5 校验行 `HARD_H5_SEMANTICS=PASS side=hard identities=144 terminal_success=144 timesteps=<n>`。
- **运行方式**：tmux 会话 `hard-v1-<日期>`，日志 `artifacts/newtask-v6/v1-hard/run.log`（`PYTHONUNBUFFERED=1`、`pipefail`、`tee`、`EXIT_CODE=` 尾行），Monitor 一次性 `until` 等待 `EXIT_CODE=`（用户 2026-09-27 口径：不设逐条进度过滤器）。预算 144 次轨迹尝试，阶段 1 与 D-1～D-3 一并申请。
- **FAIL 时的归因**：S3 跑在 `ca32e9b` 之前，V1′ 若 FAIL 要先分清是拆包引入还是审查修复引入——办法是同一入口 `--env-package robomme` 再跑一侧，预算须另批，不自动执行。
- **单测**（`tests/lightweight/test_hard_parity.py`）：参数解析、`--dry-run` 命令逐字、H5 校验对「身份缺失／难度错／末帧未完成／空文件」四类反例必拒。

### 2.3 `specs.jsonl` 指纹重算（阶段 2 末）

`hard_specs.py` 提供 `refingerprint(path, src_root)`：只重算 header `source_fingerprint`（按 `v4_specs.source_fingerprint` 同一算法对 `src/robomme_hard` 计算）并**把旧值写进 `source_fingerprint_origin`**，`identity_sha256` 因不含指纹字段而不变（`HEADER_KEYS` 里 `source_fingerprint` 属管理字段，需在 `identity_sha256` 剔除集里核对；若现实现把它算进身份，则改为不重算、只警告——以 `identity_sha256(new_header, rows) == header["identity_sha256"]` 为准）。

### 2.4 冒烟

```bash
HARD_EVAL_LIMIT=1 uv run --no-sync python scripts/evaluation_hard.py   # 临时 env 只在冒烟用；脚本本身不读它（保持与 evaluation.py 的 diff 上限）→ 冒烟改用 python -c 调 builder 单局
uv run --no-sync python -c "from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder as B; b=B('BinFill','xhard1',max_steps=50); print(b.get_episode_num()); e=b.make_env_for_episode(0); o,i=e.reset(); print(i['task_goal'][0]); e.close()"
```

## 三、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 8 处绝对 import 漏改一处 → `robomme_hard` 静默用旧 utils | `IMPORT_ISOLATED` AST 判定 + 双导入互斥让漏改立刻 `ImportError` |
| 2 | 两包同进程（如 pytest 一个 session 收集两边测试） | 互斥守卫 fail-loud；tests 全部切到 `robomme_hard`，`robomme` 只由三个上游脚本导入 |
| 3 | `source_fingerprint` 校验在用户机器上必不符 | §2.3 重算并保留原值；`load_specs` 对指纹只警告 |
| 4 | S3 期间误改 `src/robomme` 让 S3 后半段跑另一份代码 | R1；阶段 5 排在 S3 结论之后 |
| 5 | `env_metadata/train` 400 条扩展丢失 | D-3：搬到 `robomme_hard/env_metadata/train/`，README 注明 |
| 6 | 上游 `main` 在合并前又前进 | `UPSTREAM_BYTES` 判定行记 FETCH_HEAD sha；合并 PR 时以当时 sha 重跑一次 |
| 7 | `get_episode_num()` 对 xhard 档三个无梯度任务返回 0 让 `evaluation_hard.py` 的 `sum/len` 分母不变 | 分母只数实际跑过的局，与上游逻辑一致 |

## 四、盲区诚实清单

- 上游 `main` 与本 fork 分叉后的上游自身改动（`1fadc0e` 之前上游是否改过 `src/robomme`）未逐 commit 核对，只做了字节比对；如上游后续再改，`robomme_hard` 的原三档不会跟着变。
- V1′ 只证明原三档；四档在两个包名下是否逐位相同**没有对拍**（V6 口径 7：xhard 不对拍），本方案沿用。
- `hard_specs.load_specs` 下沉后 `identity_sha256` 是否含指纹字段，需实施时读 `v4_specs.identity_sha256` 确认（§2.3 两条分支）。
- `dataset_replay.py` 对 hard 演示 h5 是否可直接回放未验证，不在本方案范围。
- 4 份 train 元数据扩展（`052841a`）的下游消费者（`scripts/injection/`）在切到 `robomme_hard` 后路径是否仍指向包内 `env_metadata`，阶段 3 用 `LIGHTWEIGHT` 兜底，未单独核。

## 五、留档与 commit 纪律

- 每阶段一份 `docs/validation/newtask-v6/<日期>-hard-split-<阶段>.md`，判定行内联原文；`records/` 只放 git 还原不出的东西（V1′ 的 `h5_pairs.jsonl`、`run.log` 清洗版）。
- commit 只 add 本阶段文件，subject 接 `12.<n>`；阶段 5 的 `src/robomme` 回退单独一个 commit，body 写 `FETCH_HEAD` sha 与 `UPSTREAM_BYTES` 判定行。
- 本文件按正本第 2 条命名 `0926-robomme-hard-split-plan.md`；后续修订不改日期前缀。

## 附录 A、原第一部分（2026-09-26 初稿，内容未改，仅标题降一级）

> 裁决注（2026-09-27）：§四 D-1～D-4 全部已裁决（放行第六入口 / 整包 copy / 400 条只留 `robomme_hard` / D-4 已满足），V1′ 144 次预算已授权，见第一部分 §0.2 第 6 条。
> 勘误注（2026-09-27）：本附录 §二口径 4、§六 SPECS_IDENTITY 行、§七阶段表所写 `v6-01` 均应读作 `v6-02`；§四 D-4 已满足；§六 V1′ 行「复用 S3 运行器 `run_s3.py`」改为新入口 `scripts/parity/hard_parity.py`（第二部分 §2.2）；阶段表在阶段 0 与 1 之间新增阶段 0b（第一部分 §0.3），阶段 4 的判定行改为 `NATIVE_REGRESSION_HARD=…`。附录正文按「内容未改」原则不动。


### 一、用户与合作者的原话（逐字）

| # | 原话 | 落成口径 |
|---|---|---|
| Q1 | 「新的 robomme hard 的话最好这样 直接加个 src/robomme_hard/* scripts 里面加一个 scripts/evaluation_hard.py 这样应该不影响旧的，同时能最后都放到同一个分支上」 | 目标形态：两个并列包 + 一个并列评估入口，同一分支交付 |
| Q2 | 「src/robomme_hard/ 不影响 src/robomme/ 是独立的 / 你现在的做法是直接 改了 src/robomme/」 | 现状确认：本仓库 16 个环境文件、2 个 wrapper、7 个 utils 都改在 `src/robomme/` 里（§三实测表） |
| Q3 | 「我做了对比的机制 会有新的src/robomme_hard/ 而且传入同样参数也能生成 src/robomme/的内容」 | 硬要求 H1：`robomme_hard` 在原三档参数下产出与 `robomme` **逐位相同**（即 V1 对拍的保证要在新包名下继续成立） |
| Q4 | 「就如果说有的task 机制一样的话 robomme_hard 里面的文件会调用 robomme 里面的文件」「task本身的文件 目前全部都有改动 但是utils可能会继承一些」「全部都改动了的话，那就直接 copy 到 src/robomme_hard 里面」 | 复用方式待定：copy 还是引用（§四 D-2 给出推荐） |
| Q5 | 「src/robomme_hard/ 是新的 src/robomme 是旧的 两者互不干扰，然后在 src/robomme_hard/readme 里面说清楚改动在哪，hard 在哪」 | 硬要求 H2：`src/robomme/` = 上游原样；硬要求 H3：`src/robomme_hard/README.md` 写清改动与 hard 定义 |
| Q6 | 「两者的接口应该基本保持一致 比如 …/scripts/evaluation.py 可能只需要改 from robomme.env_record_wrapper import BenchmarkEnvBuilder 成 from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder」 | 硬要求 H4：`BenchmarkEnvBuilder` 公开签名不变，`evaluation_hard.py` 与 `evaluation.py` 只差 import 行与难度循环 |
| 用户 | 「现在已经基本完成了 除了对拍 / 现在的整个逻辑链条是什么 / 能否实现以下对话的内容 / 给出重构接口的方案 / 落到根目录md」 | 本文件 |

### 二、一句话结论与已定死口径

**能实现，而且比现状更干净**：本仓库现在把「上游原三档」和「V6 新四档」揉在同一个 `src/robomme/` 里，靠 `difficulty` 字符串族判断分叉；拆成两个包后，`src/robomme/` 直接回到上游 `main` 的字节，全部 V3～V6 改动（含录像器 `fail_safe_limit` 2000→5000 这个「被迫解冻」项）整体搬进 `src/robomme_hard/`，`BenchmarkEnvBuilder` 只在 `dataset` 参数上多认四个值 `xhard1`～`xhard4`，`scripts/evaluation_hard.py` 与上游 `evaluation.py` 的 diff 控制在两处。

已定死口径（依据小节）：

1. **`src/robomme/` 逐字节等于上游 `main` @ `1fadc0e`**（§三）——不是「等于 V1 基线 `13e5151`」。两者不同：本 fork 的 `src/robomme` 从未与上游字节相同（§三表：26 文件不同、9 文件新增、4 份 train 元数据从 100 条扩到 400 条）。
2. **`src/robomme_hard/` = 当前 `src/robomme/` 的整包复制 + 包名改写**，不做「部分引用 `robomme`」（§四 D-2，推荐 copy；理由是 ManiSkill 注册表冲突与 `utils/__init__.py` 星号导入把「逐字节相同的文件」也拖进依赖链）。
3. **公开接口不变**：`BenchmarkEnvBuilder(env_id, dataset, action_space, gui_render, override_metadata_path, max_steps)`、`get_task_list()`、`get_episode_num()`、`make_env_for_episode(...)` 签名与语义全部保留；新增只有 `dataset ∈ {"xhard1","xhard2","xhard3","xhard4"}` 与类方法 `get_difficulty_list()`（§五）。
4. **四档规格随包分发**：`scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl`（实测 256 K / 276 K / 296 K / 360 K）复制为包数据 `src/robomme_hard/env_metadata/<tier>/specs.jsonl`，`load_specs` 的封套校验从 `scripts/parity/v4_specs.py` 下沉到 `src/robomme_hard/env_record_wrapper/hard_specs.py`（src 不反向依赖 scripts 的红线不变）（§五）。
5. **原三档在 `robomme_hard` 下必须与 `robomme` 逐位相同（H1）**：验收不是新跑对拍，而是把 S3 正在跑的 V1 对拍换成「`robomme_hard` 侧 vs S0 基线」重跑 144 局（§六 V1′）；**在 S3 出结果前不动 `src/robomme/`**（S3 启动锚点 `c8c06ab` 读的是主仓活树）。
6. **V6 计划里的「冻结」项全部自然落位**：录像器在 `robomme` 回 2000 步（上游原样），在 `robomme_hard` 保持 5000；`scripts/evaluation.py` / `run_example.py` / `dataset_replay.py` 继续与上游逐字节相同；`scripts/` 顶层从五入口变六入口需用户按 P1 放行（§四 D-1）。
7. **最小用法（2026-09-27 用户确认）**：复制 `evaluation.py`，只改 import 行与 `dataset` 取值，其余逐字不动即可跑单档（第一部分 §1.1.1）。
8. **不在本方案内**：hard 演示数据（165 局）的 HF 发布、`dataset_replay.py` 的 hard 版本、网站；V6 计划 S3/S5 照旧按 `0925-newtask-release-v6-plan.md` 收尾。

### 三、现在的整个逻辑链条（回答「逻辑链条是什么」）

以下按「数据怎么来、代码怎么分叉、评估怎么进」三层写，每层给锚点。

#### 3.1 代码层：一个包、两条路径，靠难度字符串分叉

```
src/robomme/robomme_env/<Task>.py::__init__
   ├─ _resolve_sampling_config(cls, sampling_config)      # utils/sampling_config.py：拆 decision/native、assert_native_decision、fill_missing_newvalue
   ├─ SpecRecorder(native_episode_spec, task, {"seed"}, difficulty)   # utils/episode_spec.py：导出(spec=None)/回注(传冻结规格)
   ├─ normalize_robomme_difficulty(kwargs.pop("difficulty"))          # utils/difficulty.py：VALID = 原三档 ∪ {xhard1..4}
   └─ 之后每个取值点：
        if is_newvalue_difficulty(self.difficulty):  → 走 xhard 机制（utils/xhard.py 精确 OBB、unmask_swap_xhard.py、swap_uniform.py S5/O4、xhard_home_site.py …）
        else:                                        → 原三档路径（红线 N1：不新增、不挪动任何随机抽样）
```

- 原三档的「不变」不是靠字节不变保证，而是靠 **V1 对拍**：`scripts/parity/train_split_parity.py` 用官方隔离源码树 `artifacts/train-parity/local-smoke-01/official-src/`（`.official_tree` 标记 `1d4c1369…`）跑 S0 基线 144 局，再用主仓代码跑同 seed 144 局，逐局 h5 sha 相等 → `NATIVE_REGRESSION=PASS compared=144 sha_equal=144`。这就是用户说的「除了对拍」：S3 正在跑（tmux `v6-s3-20260926-01`，报告 `docs/validation/newtask-v6/20260926-s3.md` 现状 `NATIVE_REGRESSION=PENDING`，已闭合 23/144 身份前缀 sha 一致）。
- 与上游 `main` 的真实差异（2026-09-26 浅克隆逐文件 `cmp` 实测，`src/robomme` 不含 `env_metadata`）：

| 类别 | 文件 | 说明 |
|---|---|---|
| 逐字节相同 | 31 个（`__init__.py` ×3、`logging_utils.py`、5 个 wrapper、`utils/` 下 22 个） | 可原样保留 |
| 不同：16 个环境 | `BinFill.py` 495→1120 行 … `VideoRepick.py` 657→1621 行（全部 16 个） | 每个都加了 `sampling_config`/`episode_spec`/xhard 分支 |
| 不同：wrapper | `RecordWrapper.py`（+3 行：`fail_safe_limit` 2000→5000）、`episode_config_resolver.py`（+79 行：`from_v4_specs`/`v4_episodes`/`_v4_kwargs`） | 前者是 V4 用户明确授权的唯一解冻 |
| 不同：utils | `difficulty.py`、`object_generation.py`、`route.py`（`walk_config`）、`subgoal_language.py`、`subgoal_planner_func.py`、`task_goal.py`、`vqa_options.py` | `route.py` 的改动来自 10.8（2026-09-09），早于 V3 |
| fork 新增 utils | `bin_collision.py`、`episode_spec.py`、`sampling_config.py`、`swap_uniform.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py`、`unmask_swap_xhard.py`、`xhard.py`、`xhard_home_site.py` | 9 个 |
| 元数据 | `env_metadata/train/record_dataset_{VideoUnmask,VideoUnmaskSwap,ButtonUnmask,ButtonUnmaskSwap}_metadata.json` | fork 把四个 Unmask 系 train 集从 100 条扩到 400 条（2.8.1，`052841a`）；`test`/`val` 与上游相同 |
| `pyproject.toml` | 多一行 `pebble>=5.2.2` | 生成链路依赖 |

- 包内 **绝对 import** 8 处（`subgoal_planner_func.py`、`subgoal_evaluate_func.py`、`vqa_options.py`、`generate_sample_action.py`、`OraclePlannerDemonstrationWrapper.py`、`RecordWrapper.py` 等写的是 `from robomme.robomme_env…`），复制成 `robomme_hard` 后若不改写，会静默回头去 import 旧包——这是拆包时第一个要堵的洞（§六 IMPORT_ISOLATED）。

#### 3.2 数据层：四档「规格」是身份，不是 seed

```
源码申报 ──train_split_config extract --release newtask-v6──▶ scripts/configs/newtask-v6/sampling_config.json（88 K，含 16 任务 decision/native）
   └─▶ v4_specs draw --difficulty <tier> --seed-profile v6   （seed 偏移 xhard4 6e6 / xhard1 8e6 / xhard2 10e6 / xhard3 12e6；只 reset 不 step）
        └─▶ freeze ──▶ scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl（header：sampling_config 全文、源码指纹、runtime 四项、seed_rule、identity_sha256；行：selected=0/3/6 的候选规格）
              └─▶ v4_rollout run（GL）──▶ 165 局正式 h5/视频（artifacts/newtask-v6/v6-01/<tier>/…，待 S3 接纳）
```

评估侧起环境时**不再抽签**：`BenchmarkEnvBuilder.from_v4_specs(env_id, header, specs_by_identity)` 把 `seed / difficulty / sampling_config / native_episode_spec` 从 `specs.jsonl` 行里取出传给 `gym.make`，`SpecRecorder` 进入回注模式，每个取值点用冻结值、原抽样照常发生只作核验（`scripts/eval/v4_eval.py::_binding` 读 `env.unwrapped._spec` 报 `mismatch/unused`）。这条路径目前只有 `scripts/eval/v4_eval.py` 在用，且 `load_specs` 住在 `scripts/parity/v4_specs.py`——**src 不能反向依赖 scripts**，所以现在没有任何 `src` 内的公开入口能按档名直接起 xhard 环境。这是拆包时接口要补的唯一一块。

#### 3.3 评估层：上游只认 `dataset="test"` 的 metadata

上游 `scripts/evaluation.py`：`BenchmarkEnvBuilder(env_id=task, dataset="test", action_space="joint_angle", max_steps=1300)` → `_resolve_metadata_path` 读包内 `env_metadata/test/record_dataset_<task>_metadata.json`（每条 `seed/difficulty/episode`）→ `gym.make(env_id, seed=…, difficulty=…)`。`dataset` 只允许 `{train,test,val}`（`_ALLOWED_DATASETS`）。四档评估目前只能走 `python -m scripts.eval.v4_eval --specs …`，与上游入口不是同一个形状。

### 四、待用户裁决的四项（未裁决不开工）

| # | 问题 | 推荐 | 不选推荐的代价 |
|---|---|---|---|
| D-1 | `scripts/evaluation_hard.py` 触碰 P1「顶层只许五入口」 | **放行第六入口**，P1 清单改为六项并写明与 `evaluation.py` 的 diff 上限（两处） | 退而放 `scripts/eval/evaluation_hard.py`，但合作者要的「改一行 import 就能用」体验变差 |
| D-2 | `robomme_hard` 对 31 个逐字节相同文件是 copy 还是 `from robomme… import *` 引用 | **整包 copy，零跨包 import**（§五 5.1 给三个硬理由） | 引用会让 `robomme_hard` 强依赖 `robomme`，且两包同进程各自 `register_env("BinFill")` 必撞（ManiSkill `register_env` 对重复 id 默认 `raise RuntimeError`） |
| D-3 | 四个 Unmask 系 train 元数据 100→400 条的扩展留在哪 | **只留在 `robomme_hard/env_metadata/train/`**，`robomme` 回上游 100 条 | 留在 `robomme` 就违反 H2「旧包 = 上游原样」 |
| D-4 | 拆包时点 | **S3 拿到 `NATIVE_REGRESSION` 结论后再动 `src/robomme/`**；在此之前只做不碰 `src/` 的准备（第二部分阶段 0） | S3 启动锚点 `c8c06ab` 读的是活树，中途改 `src/robomme` 会让 S3 后半段跑在另一份代码上 |

用户已在 V6 计划 D7 m13 给过「`src/robomme/` 改动免逐项批准、改完出报告」，但那是对 V6 新值改动的授权；**本方案把 `src/robomme/` 整体回退到上游**属于新范围，按 P2 须另行批准。

### 五、重构后的接口与包结构 （初稿内容，已被 §〇′.2／§〇′.6 取代）

#### 5.1 目录（改动一览：文件 / 来源 / 改什么）

| 路径 | 来源 | 改什么 |
|---|---|---|
| `src/robomme/**` | 上游 `main` @ `1fadc0e` 的 `src/robomme/**` 逐文件覆盖（含 `env_metadata/`） | 删 fork 新增的 9 个 utils；`RecordWrapper.py` 回 2000 步；`episode_config_resolver.py` 回 247 行 |
| `src/robomme_hard/**` | 当前 `src/robomme/**` @ 本方案 Beta 锚点整包复制 | ①包名：8 处绝对 import `robomme.` → `robomme_hard.`（或改相对）；②`env_record_wrapper/episode_config_resolver.py`：`from_v4_specs` 收编进 `__init__` 的 `dataset` 分支（5.2）；③新增 `env_record_wrapper/hard_specs.py`（5.3）；④新增 `env_metadata/xhard{1,2,3,4}/specs.jsonl`；⑤新增 `README.md`（5.5） |
| `src/robomme_hard/__init__.py` | 新 | 导入时若 `"robomme.robomme_env" in sys.modules` 则 `raise ImportError("robomme 与 robomme_hard 不能同进程导入：ManiSkill 注册表按 env_id 唯一")`；反向在 `robomme` 侧**不加**（旧包不改） |
| `scripts/evaluation_hard.py` | `scripts/evaluation.py` 复制 | 只改两处：import 行；`for task in TASKS` 外面套 `for tier in BenchmarkEnvBuilder.get_difficulty_list()`，`dataset=tier`；`max_steps` 注释加一句「xhard 档不受 1301 限制，见 V6 口径 2」（值本身由用户定，默认仍 1300） |
| `scripts/eval/v4_eval.py`、`scripts/parity/*.py`、`scripts/injection/**`（14 文件）、`tests/**`（45 文件） | 现有 | `from robomme.` → `from robomme_hard.`（机械替换，AST 校验零残留）；`v4_specs.load_specs` 改为薄包装调用 `robomme_hard.env_record_wrapper.hard_specs.load_specs` |
| `pyproject.toml` | 现有 | `packages = ["src/robomme", "src/robomme_hard"]` |
| `AGENTS.md` P1/P2 | 现有 | P1 清单加第六入口（D-1 放行后）；P2 `<PROTECTED_DIRS>` 扩为 `src/robomme/`（冻结 = 上游原样）+ `src/robomme_hard/`（逐个批准） |

**D-2 推荐 copy 的三个硬理由**：①ManiSkill `register_env` 对重复 id 在 `override=False` 时 `raise RuntimeError`（`.venv/lib/python3.11/site-packages/mani_skill/utils/registration.py::register_env`），两包各自装饰 `@register_env("BinFill")`，任何跨包 import 都会把两套注册拉进同一进程；②`utils/__init__.py` 虽逐字节相同，但它星号导入 `subgoal_planner_func`、`object_generation` 等**不相同**的模块，引用它等于引用旧实现；③H1 要求的是「行为逐位相同」，拆包后由 V1′ 对拍保证，不需要用共享字节来保证。

#### 5.2 `BenchmarkEnvBuilder`（`robomme_hard` 版）签名与语义

```python
class BenchmarkEnvBuilder:
    _ALLOWED_DATASETS = {"train", "test", "val"} | set(NEWVALUE_DIFFICULTIES)   # 后者 = ("xhard1","xhard2","xhard3","xhard4")

    def __init__(self, env_id, dataset="test", action_space="joint_angle",
                 gui_render=False, override_metadata_path=None, max_steps=10000):
        # 签名与上游逐字相同；只多认四个 dataset 值
        if is_newvalue_difficulty(dataset):
            header, _, rows = hard_specs.load_specs(self._resolve_specs_path())   # 包内 env_metadata/<tier>/specs.jsonl
            self._hard = {"sampling_config": header["sampling_config"][env_id], "recovery_rule": header.get("recovery_rule"),
                          "rows": {int(r["episode"]): r for k, r in rows.items() if k.split("/")[0] == env_id}}
            self.metadata_index = {}
        else:
            self._hard = None
            self.metadata_index = load_episode_metadata(self._resolve_metadata_path())   # 与上游同一条路

    @classmethod
    def get_task_list(cls): ...            # 不变：16 任务固定序
    @classmethod
    def get_difficulty_list(cls): return list(NEWVALUE_DIFFICULTIES)   # 新增；MoveCube/InsertPeg/StopCube 只在 xhard4 有行，其余档 get_episode_num()==0
    def get_episode_num(self): ...         # xhard 档 = 该任务 selected 行数（3）；原三档不变
    def make_env_for_episode(self, episode_idx, max_steps=None, include_*...): ...   # 不变；xhard 档 env_kwargs.update(self._hard_kwargs(episode_idx))
```

- `override_metadata_path` 在 xhard 档下解释为「含 `<tier>/specs.jsonl` 的目录」，与原三档「含 `record_dataset_<task>_metadata.json` 的目录」平行，不新增参数。
- `from_v4_specs` 保留为 `@classmethod` 薄包装（`scripts/eval/v4_eval.py` 的 `--specs` 任意路径用法不断），内部走同一 `_hard` 结构。
- **episode 编号语义**：xhard 档 `episode_idx` = specs 行里的候选序号（0/3/6），不是 0..2；`get_episode_num()` 返回 3 但可评 episode 要用 `hard_episodes()`（= 现 `v4_episodes()`）。为了让 `evaluation_hard.py` 与 `evaluation.py` 的 `for episode in range(episode_count)` 循环体不改，推荐**在 `_hard` 构造时把行按候选序升序重编为 0..n-1**，原候选序号保留在 `info["hard_candidate_index"]`（⚠ 陷阱：重编号只影响 builder 侧索引，规格行本身与 `identity_sha256` 不动，否则 §六 SPECS_IDENTITY 必炸）。

#### 5.3 `hard_specs.py`（从 `scripts/parity/v4_specs.py` 下沉的只读部分）

只搬 `load_specs()` 与它依赖的纯函数：`canonical_json`、`digest`、`identity_sha256`、`HEADER_KEYS`、`seed_rule_for`、`_known_seed_rule`；**不搬 `draw`/`freeze`**（抽签与冻结留在 `scripts/parity/`，它们要起环境、写文件）。`load_specs` 现有的封套校验（`sampling_config_sha256` 自洽、每行 `spec_sha256`、`identity_sha256`、runtime 四项与 builder 的 `gym.make` 参数逐字相等）一条不少；源码指纹校验（`source_fingerprint`）在包内改为**只警告不拒绝**——发布后用户机器上的源码 sha 就是包自己的 sha，指纹应在打包时重算写回 header，第二部分 §2.3 给命令。

#### 5.4 `scripts/evaluation_hard.py` 与 `evaluation.py` 的 diff（上限）

```diff
-from robomme.env_record_wrapper import BenchmarkEnvBuilder
+from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder
 ...
 TASKS = BenchmarkEnvBuilder.get_task_list()
+TIERS = BenchmarkEnvBuilder.get_difficulty_list()   # xhard1..xhard4
 ...
-for task in TASKS:
-    env_builder = BenchmarkEnvBuilder(env_id=task, dataset="test", ...)
+for tier in TIERS:
+  for task in TASKS:
+    env_builder = BenchmarkEnvBuilder(env_id=task, dataset=tier, ...)
+    if env_builder.get_episode_num() == 0: continue      # MoveCube/InsertPeg/StopCube 只有 xhard4
```

视频落盘名加 `tier`，其余逐字不动。判定：`diff scripts/evaluation.py scripts/evaluation_hard.py | grep -c '^[<>]'` ≤ 12。

#### 5.5 `src/robomme_hard/README.md` 必含内容（H3）

①一句话：hard = 四档 `xhard1<xhard2<xhard3<xhard4`，原三档在本包下与 `robomme` 逐位相同（附 V1′ 判定行原文）；②四档定稿表（从 `0925-newtask-release-v6-plan.md` 第一部分 §三逐字搬，含备注列）；③「改动在哪」表：由脚本 `scripts/parity/hard_pkg_manifest.py` 生成，逐文件列「与 `src/robomme` 相同 / 不同（+x/−y 行）/ 本包新增」，README 里内联生成结果并写生成命令；④机制说明：`sampling_config` 两块结构、`SpecRecorder` 导出/回注、`specs.jsonl` 封套、seed 偏移公式；⑤使用：`evaluation_hard.py` 三行示例 + `override_metadata_path` 用法；⑥红线：两包不可同进程导入、xhard 不受 1301 步限制、`fail_safe_limit=5000`。

### 六、验收（查什么 / 怎么查 / 过了说明什么 / 判定行） （初稿内容，已被 §〇′.8 取代）

| 项 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| UPSTREAM_BYTES | `src/robomme/**` 与上游逐字节相同 | `git diff --stat <上游 main 树> HEAD -- src/robomme/`（上游以 `git fetch <url> main` 到 `FETCH_HEAD` 取）为空；另 `cmp` 三个冻结脚本 | H2 成立；上游合并时 `src/robomme` 零 diff | `UPSTREAM_BYTES=PASS files=<n> diff=0` |
| IMPORT_ISOLATED | `robomme_hard` 包内没有任何 `robomme.` 绝对引用；同进程双导入被拒 | AST 遍历 `src/robomme_hard` 全部 `Import`/`ImportFrom`，模块名以 `robomme.` 开头计数；`uv run python -c "import robomme.robomme_env, robomme_hard"` 期望 `ImportError` | copy 方案没有静默回头依赖旧包 | `IMPORT_ISOLATED=PASS abs_refs=0 dual_import=REJECTED` |
| SPECS_IDENTITY | 包内四份 `specs.jsonl` 与 `scripts/configs/newtask-v6/v6-01/<tier>/` 的 `identity_sha256` 相等 | `hard_specs.load_specs` 各加载一次，比对 header 字段 | 分发的规格就是 S4 生成用的那份 | `SPECS_IDENTITY=PASS tiers=4 rows=165` |
| **V1′** | `robomme_hard` 原三档 vs S0 基线 144 局 h5 sha | 复用 S3 运行器 `run_s3.py` 的路径 B，只把 `PYTHONPATH`/import 切到 `robomme_hard`；比较 `compare/h5_pairs.jsonl` | H1 成立：同参数产同内容 | `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144 field_mismatch=0` |
| HARD_EVAL_SMOKE | `evaluation_hard.py` 链路能跑 | 单 tier、单任务、单 episode（`--limit` 用临时 env `HARD_EVAL_LIMIT=1`，不改脚本）；`DummyModel` 跑到 `terminated/truncated` | 接口闭环 | `HARD_EVAL_SMOKE=PASS tiers=1 tasks=1 episodes=1 status=<任意>` |
| LIGHTWEIGHT | 现有轻量测试在改 import 后失败/错误集合是 S0 的子集 | 沿 V6 §5.3 四片各 280 s | 机械替换没打坏测试 | `LIGHTWEIGHT=PASS new_failures=0 new_errors=0` |
| EVAL_PY_UPSTREAM / ENTRIES | 三脚本逐字节同上游；顶层入口数 | `cmp`；`ls -1 scripts/*.py \| wc -l` = 6（D-1 放行后） | 冻结项未破 | `EVAL_PY_UPSTREAM=PASS ENTRIES=6` |
| DIFF_CAP | `evaluation_hard.py` 与 `evaluation.py` diff 行数 | `diff … \| grep -c '^[<>]'` | H4 成立 | `EVAL_HARD_DIFF=PASS lines=<n≤12>` |

V1′ 为什么能逐位：`robomme_hard` 的原三档路径与现 `src/robomme` 是同一份字节（copy），只改包名与 import；随机流由 `torch.Generator(seed)` 决定、与包名无关；S3 已在证明现 `src/robomme` 的原三档与 S0 基线逐位相同，V1′ 只是把「被测包」换名再证一次，所以两者要么同过、要么同挂。

### 七、实施步骤表（阶段 / 内容 / 判据） （初稿内容，阶段 2～5 已被 §〇′.9 取代）

| 阶段 | 内容 | 判据 | 是否碰 `src/` |
|---|---|---|---|
| 0 准备（可在 S3 结束前做） | 取上游 `main` 快照并固化 sha；写 `hard_pkg_manifest.py`（只读 diff 工具）；写 `hard_specs.py` 草稿放 `scripts/parity/`（先不下沉）；写 `evaluation_hard.py` 草稿放 scratchpad | `UPSTREAM_BYTES` 的对照表先出（现状 26 不同 / 9 新增，作为阶段 2 的期望） | 否 |
| 1 裁决 | D-1～D-4 逐条拿用户答复；P2 批准清单：「`src/robomme/**` 整体回上游」「新建 `src/robomme_hard/**`」两条 | 用户逐条同意原话写进本文件 §一 | 否 |
| 2 建 `robomme_hard` | `cp -a src/robomme src/robomme_hard`；改 8 处绝对 import；加 `__init__` 互斥；收编 `from_v4_specs`；下沉 `hard_specs.py`；复制四份 `specs.jsonl`；改 `pyproject`；`uv sync` | `IMPORT_ISOLATED`、`SPECS_IDENTITY` | 只新增 |
| 3 切换调用方 | 14 个 scripts 文件 + 45 个 tests 文件 import 替换；`v4_specs.load_specs` 改薄包装；`evaluation_hard.py` 落顶层 | `LIGHTWEIGHT`、`EVAL_HARD_DIFF`、`ENTRIES=6` | 否 |
| 4 V1′ 对拍 | 按 §六 跑 144 局（约 50 min 单卡，S0 实测 2994 s；须 tmux + Monitor；预算 144 次轨迹尝试，属 P3 阈值内须用户在阶段 1 一并授权） | `NATIVE_REGRESSION_HARD=PASS` | 否 |
| 5 回退 `src/robomme` | 用上游树覆盖 `src/robomme/**`（含 `env_metadata`）；`git rm` 9 个新增 utils | `UPSTREAM_BYTES=PASS`、`EVAL_PY_UPSTREAM=PASS`、`HARD_EVAL_SMOKE` | **是（P2）** |
| 6 文档与规则 | `src/robomme_hard/README.md`；`AGENTS.md` P1/P2 改写；账本追加；`docs/validation/newtask-v6/<日期>-hard-split.md` 报告 | `git diff --check`；README 内联全部判定行原文 | 否 |

实施完成后实测结果以子节追加在本表之后，不改写原计划。


## 附录 B、legacy 清单（2026-09-27，只读盘点；删除须用户逐组勾选后另起一轮执行）

用户原话：「告诉我有哪些 legacy 文件可以删除 我只需要 v6 的几阶段来完成 … 的重构」。分组原则：**A** 不在 V6 四阶段 + V1′ 的闭包内、也不被保留测试引用 → 可删；**B** 历史留档、git 可追溯、删不删由用户定；**C** 必须保留；**D** 他人在途、不动。引用关系由 `grep`（含裸 import，`scripts/parity/__init__.py` 往 `sys.path` 插目录）与 `git ls-files` 实测。

### 表 0　V6 四阶段 + V1′ 的依赖闭包（这就是要保留的最小集合）

| 类别 | 文件 | 谁用 |
|---|---|---|
| 入口 | `scripts/parity/train_split_config.py`（阶段 1）、`v4_specs.py`（2a/2b）、`v4_rollout.py`（2c）、`v5_generation.py`（2a～2c 一键管道，审查修复三席用的就是它）、`scripts/eval/v4_eval.py`（3） | 第一部分 §三 |
| 被入口 import | `scripts/seed_layout.py`（`train_split_config`、`v4_specs`、`train_split_parity`、`train_split_audit`、`v6_tier_monotone` 裸 import）；`train_split_runner.py`（`v4_rollout` subprocess）→ `train_split_worker.py`；`train_split_parity.py`（`v4_rollout::compare_h5_pair`、V1′ 比较器）→ `train_split_comparison.py` ↔ `comparator_fixtures.py`；`train_split_audit.py`（`test_v4_xhard_unmaskswap`/`videoplace` 用）；`scripts/injection/candidates/io.py` 的 `canonical_json`/`digest`（`v4_specs.py` 唯一的 injection 依赖，阶段 0b 内联） | 依赖闭包盘点 |
| V6 收尾 | `scripts/parity/{v6_candidate_values,v6_tier_monotone,v6_v0_native_definitions,v6_site_catalog,v6_site}.py`、`v6_site.html` | 各自 `test_v6_*` |
| 配置 | `scripts/configs/newtask-v3/{subset_manifest,train_manifest}.json` + `official_train/`（`train_split_parity.DEFAULT_FROZEN_DIR`、`train_split_audit`）；`newtask-v4/sampling_config.json`（`v4_specs.DEFAULT_SAMPLING`）；`newtask-v5/sampling_config.json`（`v6_v0_native_definitions`、CLAUDE.md 核实清单）；`newtask-v6/{sampling_config.json,v6-01/,v6-02/}`（`v6-01` 仍被 `v5_generation` 路径模板与 `test_v5_generation_tools` 引用） | grep |
| 产物 | `artifacts/train-parity/local-smoke-01/official-src/`（`--official-root` 官方源码树，`.official_tree=1d4c1369…`）；`artifacts/newtask-v6/v1/base/`（S0 基线 144 局 49 GB，V1′ 对照侧，用户明令保留）；`artifacts/newtask-v6/v6-02/`（现行 165 局 112 GB）；`artifacts/newtask-v6/{s4-relaunch-02,audit-fix-02}`（v6-02 验收链）；`artifacts/newtask-v6/{site-v11,site-v12}` | 第二部分 §2.2、审查修复留档 |

### A　可删（git 跟踪的代码、测试、配置、留档）

| 路径 | 规模 | 依据 |
|---|---|---|
| `scripts/injection/**`（`candidates/` 11 文件、`rollout/` 12 文件、`delivery.py`、`hf_release.py`、`_migrate_run10.py`、`__init__.py`） | 27 跟踪文件 | V2 注入流程（`INJECTION_REFACTOR_PLAN.md`）；V6 只用 `candidates/io.py` 两个纯函数，先内联进 `v4_specs.py`；`hf_release.py` 是运行 10 的 HF 发布器，`_migrate_run10.py` 只被 `test_injection_migration` 引用，`rollout/{figure_parity,single_binfill}.py` 无人引用 |
| `scripts/parity/{v4_combos,v4_demo_probe,v4_reset_probe,v4_spec_negative}.py`、`scripts/configs/newtask-v4/combos.json` | 5 文件 | V4 探针；零测试引用，只被 0922/0924 计划与 v4/v5 留档提到 |
| `scripts/parity/{calibrate,compare_vs_original}.py`、`tolerance.json`、`gl/`（2 文件）、`results/`（79 文件） | 83 文件 | V3 容差对拍（ada/a6000/a40 标定，`scripts/parity/README.md`）；V6 的 V1 走严格 sha 路径 `train_split_parity`，不用容差档；零测试引用 |
| `tests/_shared/{parity_keyframes,parity_observer,parity_review,parity_runner,parity_worker_isolation,action_freeze_campaign,parallel_calibration,native_sampling_parity,contract_builder_fixture,frozen_injection}.py`、`tests/_shared/parity_sitecustomize/` | 11 项 | 全部只服务 V2 对拍与 injection（保留 `tests/_shared/{__init__,dataset_generation,repo_paths}.py`，上游原有） |
| `tests/lightweight/{test_candidate_loader,test_candidates_refactor,test_env_check,test_episode_specs,test_episode_timeout,test_hf_release,test_injection_blocks,test_injection_campaign,test_injection_contract,test_injection_delivery,test_injection_migration,test_operand_scope,test_refactor_figures,test_reset_pipeline,test_rollout_parity,test_rollout_state,test_window_timeline,test_native_sampling_config,test_native_sampling_evidence,test_action_freeze_delivery,test_action_freeze_campaign}.py`、`tests/dataset/test_native_sampling_parity.py` | 22 文件 | import A 组模块或读 `scripts/configs/newtask-v2`／`docs/validation/newtask-v2`；`test_env_check` 还引用早已不存在的 `scripts/injection/env_check.py` |
| `scripts/configs/newtask-v2/`（3 文件）、`newtask-v3/history/`（4）、`newtask-v4/v4-01/`（2）、`newtask-v5/v5-01/`（2） | 11 文件 | 只被 A 组代码／测试或历史文档读；`v4-01` 被 `test_v5_xhard_videounmask_buttonunmask.py` 以绝对路径引用一处、`v5-01` 被 `test_v5_generation_tools.py` 引用一处，删前改这两处夹具 |
| `docs/validation/newtask-v2/**` | 115 文件、8.2 MB | 只被 A 组测试读取（`cases.json`、证据包） |
| `INJECTION_REFACTOR_PLAN.md`、`NEWTASK_V2_PLAN.md` | 2 文件 | 只被 `AGENTS.md` 历史账本与 v2 留档引用（账本条目不改，死链可接受） |
| `artifacts/injection/**`（320 跟踪文件、121 MB）、`artifacts/test-tmp/`（940 MB，514 个测试临时目录）、`artifacts/cache/`（144 MB uv 缓存）、`artifacts/codex-multiagent/`（5.6 MB）、`artifacts/logs/`（236 KB） | — | 与 A 组同源／临时／缓存；`artifacts/injection` 是唯一有 git 跟踪的 `artifacts` 子树，删时 `git rm -r --cached` 一并处理 |

### B　V6 之前的全部 + V6 中间产物（**已裁决：归档经验教训进 `docs/`，其余删除；不再做 V2～V5 任何对拍与生成**）

用户 2026-09-27 原话：「历史教训小文件留档 进入 …/docs 其他的全部进入删除 只保留git历史」「我要的是归档V6 之前的 不再做对拍也不再生成 只作为经验教训」。落地规则（执行顺序见第一部分 §0.3 表）：

1. **去处只有两种**：①经验教训文本 → `docs/`；②其余删除。跟踪文件靠 git 历史恢复；`artifacts/` 全部未跟踪，**搬进 `docs/` 的那份就是唯一副本**，所以保留清单由脚本从 docs 引用生成（§0.3 步骤 4），不靠人手。
2. **进 `docs/` 的**：`docs/validation/newtask-v2～v5/` 原地不动；三份旧计划 `git mv` 到 `docs/plans/`；`artifacts` 里被 docs/账本引用或属显式验收依赖的小文件（判定行来源、授权记录、事故记录、运行脚本与清洗后日志、审查汇总）复制到 `docs/validation/<版本>/records/legacy/<原二级目录>/`，附 `MANIFEST.md`。
3. **删除（跟踪）**：表 A 全部；`scripts/generate_dataset_newseed.py`（P1 改四入口，D-1 放行后 `evaluation_hard.py` 为第五入口）；`tests/lightweight/{test_swap_schedule_generic,test_binfill_demo_duplicate}.py`（只依赖它）；`test_h5_parity_compare`、`test_native_restore_step2` 若测试对象已不存在则删。
4. **删除（未跟踪 `artifacts/`）**，逐目录显式列名：`artifacts/newtask-v4`（31 GB）、`artifacts/newtask-v5`（32 GB）、`artifacts/audit`（1.1 GB）、`artifacts/newtask-v6/{v6-01,v6-01-infra-recovery-01,v6-s2-20260926-01,v6-s3-20260926-01,gl-smoke-61890467-binf-xhard1-20260926T195419Z,s3-slow-investigation,s0,s1-reset,s2-prep,s4-prep,s4-launch,plan-probes,vpb-order-fix-prep,site,site-v2,site-review,site-v3,site-v4,site-v5,site-v6,site-v7,site-v8,site-v9,site-v10}`。删前必须已 `LEGACY_KEEP=PASS`、`LEGACY_ARCHIVE=PASS`。
5. **明确保留（表 C）**：`artifacts/newtask-v6/v1/base`（S0 基线 144 局 49 GB，**V1′ 对照侧，用户明令保留对拍**）、`v6-02`、`s4-relaunch-02`、`audit-fix-02`、`site-v11`、`site-v12`、`artifacts/train-parity/local-smoke-01/official-src`。

下表保留为盘点原文（「说明」列的「建议留」「由用户定」已被上述裁决覆盖）：


| 路径 | 规模 | 说明 |
|---|---|---|
| `0921/0922/0924-newtask-release-v{3,4,5}-plan.md` | 3 文件、400 KB | 被 `train_split_parity/audit`、`v4_specs`、`v5_generation` 的 docstring 与 `test_v4_xhard_*`/`test_v5_*` 注释以链接引用（删了只是死链）；**建议留** |
| `docs/validation/newtask-v{3,4,5}/` | 60 文件、<1 MB | 代码不读 |
| `tests/lightweight/{test_swap_schedule_generic,test_binfill_demo_duplicate,test_h5_parity_compare,test_native_restore_step2}.py` | 4 文件 | 前两者只依赖 `generate_dataset_newseed.py`（随下一行裁决）；后两者只依赖 `repo_paths`，实施时看测试对象是否仍存在再定 |
| `scripts/generate_dataset_newseed.py` | 1 文件 | **不在 V6 闭包内**，只被 A 组与上一行引用；但它是 P1 五入口之一，删除须用户明确改 P1 清单为四入口 |
| `artifacts/newtask-v4/`、`artifacts/newtask-v5/` | 31 GB、32 GB | 旧规格产物；规格文件本身已在 git |
| `artifacts/newtask-v6/{v6-01（94 GB）,v6-01-infra-recovery-01（18 GB）,v6-s2-20260926-01（73 GB）,v6-s3-20260926-01（49 GB）,gl-smoke-61890467-…（795 MB）,s3-slow-investigation（361 MB）,s0（361 MB）,plan-probes（154 MB）,s1-reset,s2-prep,s4-prep,s4-launch,vpb-order-fix-prep,site,site-v2,site-review,site-v3～site-v10}` | 约 236 GB | S2/S3 结论与 v6-01 对照已写进 `docs/validation/newtask-v6/`；用户 2026-09-24 口径「收尾只保留最终产物」支持删；`v6-s3` 删前确认 `compare/summary.json` 已在 `records/`；`s4-launch/` 含 S4 事故与恢复批准记录，建议只删其中大文件 |
| `artifacts/audit/`（5 个 `v6-semantic-*`） | 1.1 GB | 两轮审查证据，结论已在 `0926-v6-audit-fix-plan.md` 第七、八节 |

### C　必须保留

`src/robomme/**`（回上游由阶段 5 处理）；`scripts/{evaluation,run_example,dataset_replay,seed_layout}.py`；表 0 全部；`scripts/parity/{manifest_16x3.json,identities_16x3.txt,README.md,__init__.py}`、`scripts/README.md`；`tests/` 其余（上游 29 文件 + `test_v4_*`、`test_v5_*`、`test_v6_*`、`test_bin_collision`、`test_sampling_config_split`、`test_comparator_scope`、`test_train_split_parity`、`test_scripts_do_not_import_tests` 等）；`docs/validation/newtask-v6/**`、`docs/README.md`、`docs/greatlakes.md`、`docs/maniskill-robomme-multiprocess.md`、`docs/validation/README.md`；三份 0925/0926 计划；上游原有 `challenge_interface/`、`doc/`、`Dockerfile`、`.dockerignore`、`readme.md`、`LICENSE`。

### D　他人在途，不动

`logs/`、`scripts/configs/newtask-v6/smvla-smoke-0927/`、`scripts/parity/v6_gt_lengths.{py,json}`、`M scripts/parity/v6_site.{html,py}`、`artifacts/newtask-v6/smvla-0927{,-more,-fill,-smoke}`（约 2 TB）、tmux `smvla-site-8060`、`corlvis-site`。
