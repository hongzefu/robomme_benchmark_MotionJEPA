# 拆包阶段 2：`scripts/` 重组、injection-dev 两阶段链路、三侧对拍入口、tests 三类处理（2026-09-28）

计划：`docs/plans/0927-robomme-hard-layered-plan.md` 第一部分 §3.5、§五、§六，第二部分 §1.3。起点 HEAD `12.206`。本阶段不改 `src/robomme`。

## 一、改动

- **`scripts/injection-dev/`**（连字符目录，入口按路径直跑，`_common.py` 负责 `sys.path`）：
  - `_extract.py`（①定规则，`train_split_config.extract_task(pkg=…)`）、`_draw.py`（②抽签，由 `v4_specs` 搬来，包名参数化，子进程初始化后断言注册归属，返回 `(rows, draw_stats)`）、`_freeze.py`（③封存：完整选签含 MoveCube 分层，`hard-specs/2`，`os.link` 排他落盘；含 `freeze_equiv`）、`freeze_specs.py`（第一阶段入口，`--dry-run`／`--self-check`）；
  - `_rollout.py`（第二阶段：`SpecsLock` 先于一切 O_EXCL 取锁、continue 状态机与递补、基础设施失败每身份最多重跑 1 次、持锁回写核整份文件 sha 与身份不变、resume 的 UNKNOWN 检测、replay 只读重放与 `REPLAY_SET`）、`generate_h5.py`（第二阶段入口）、`_report.py`（`HARD_GENERATION=REPORT`，计数显式零值）；
  - `site/`：`git mv` 自 `scripts/parity/` 的 8 个出图／核对文件，`parents[2]`→`parents[3]`，默认配置改读包内 xhard4 header（与原 V6 快照逐任务相同，已核）；`v6_candidate_values` 的来源指纹检查改为「各档草稿来源指纹彼此一致」；共用读写放 `site/site_io.py`。
- **`scripts/parity/`**：`train_split_runner.py`（`--official-root` 默认 vendor、核 `SOURCE.json`；vendor 下 `--src-root` 必填；新增 `--metadata-root`（默认 `scripts/configs/newtask-v3/official_train`，核 `records_sha256=a57655d6…`）显式传给官方 `read_train_metadata`；formula 分支延迟导入 `robomme_hard` 的 seed 规则；逐局追加 `results.partial.jsonl` + fsync、`--resume`）；`train_split_worker.py`（`ROBOMME_ENV_PACKAGE` 决定导入包，结果记 `env_package`／`env_module`／`wrapper_modules`）；`train_split_config.py`（`extract_task(pkg=)`、CLI `--pkg`，默认 release 改 newtask-v6、缺省落点改到 `artifacts/`）；`hard_parity.py` 重写为 generate／publish／compare／import-s4／binding；`hard_regression.py`（阶段 1 已建）。
- **第五入口** `scripts/evaluation_hard.py`。
- **删除**：`scripts/parity/{v4_specs,v4_rollout,v5_generation,legacy_keep_list}.py`、`identities_16x3.txt`、`manifest_16x3.json`、`scripts/eval/`、`scripts/configs/newtask-v4/`、`newtask-v5/`、`newtask-v6/{sampling_config.json,v6-01/}`；未跟踪的 `scripts/injection/`（删前列清单：只剩 26 个 `__pycache__` 文件，无源码）。`scripts/parity/results/` 按计划不删。
- **tests 三类处理**：
  1. 引用已删／已搬脚本：删 `test_v4_specs.py`、`test_v4_env_builder.py`、`test_v5_generation_tools.py`、`test_v6_v0_native_definitions.py`（旧 API／旧快照已不存在）；改路径 `test_v6_audit_fix_scripts.py`、`test_v6_difficulty_tiers.py`、`test_v6_candidate_values.py`、`test_v6_tier_monotone.py`、`test_v6_site_labels.py`、`test_v6_site_v11.py`；`test_sampling_config_split.py` 的快照测试改为「robomme_hard 源码提取 == 包内 header」；`test_v6_swap_uniform.py` 删一个读旧快照的用例；`test_hard_parity.py` 改写为新入口的纯 CPU 测试（7 例）；新增 `test_hard_state_machine.py`（4 例）。
  2. 测新值／改动行为的 35 个文件改测 `robomme_hard`：模块引用替换 155 处、源码路径 13 处，逐文件计数见 commit body；文件顶加一行注释说明。
  3. `test_TaskGoal.py` 恢复为官方 1fadc0ec 原文，新值族 3 组用例拆到 `test_TaskGoal_newvalue.py`（测 robomme_hard 的 task_goal）。有意测官方的文件（tests/dataset/*、`_shared`、与上游逐字节相同的 lightweight 测试）保持原样。

## 二、判定行

```text
FREEZE_EQUIV=PASS tiers=4 rows=550 selected_equal=165
STATE_MACHINE=PASS cases=4
FREEZE_ONLY_JSONL=PASS files_written=1        （BinFill,PickXtimes × xhard1 × 1 候选，--max-reset-attempts 5，--workers 2，GPU 1；实耗 reset 2）
ROLLBACK_WRITE=PASS identity_unchanged=1 delivered=1   （同一冒烟 jsonl，--tasks BinFill，1 局 rollout，59 s）
NATIVE_SMOKE=PASS sides=2 gpu=Ada mode=dev    （O：vendor 编排 + 官方 1fadc0ec 源码 + 官方 _worker；H：镜像 worker + robomme_hard；
                                               各 PickXtimes/0 easy 1 局，两侧 h5 sha 同为 605a26cb…；运行时判定行标签误打成 SHARD_SMOKE，已修为 NATIVE_SMOKE）
HARD_EVAL_SMOKE=PASS task=BinFill episode=0 tier=xhard1 seed=8400000 episodes=80 max_steps=1500 status=smoke_cut steps=50 injected_mismatch=0
EVAL_PY_UPSTREAM=PASS ENTRIES=5               （dataset_replay／evaluation／run_example 与 git show 1fadc0ec 逐字节 cmp 相同；ls -1 scripts/*.py | wc -l = 5）
EVAL_HARD_DIFF=PASS lines=7                   （见下方说明）
TESTS_COLLECT=PASS errors=0 stray_official=0  （pytest tests/ --collect-only：1295 tests collected，0 error）
```

- **`EVAL_HARD_DIFF` 与计划数字不同**：计划写 `lines=8`；实测 `diff scripts/evaluation.py scripts/evaluation_hard.py | grep -c '^[<>]'` = 7。差异恰为计划所列 4 处（import 行、`dataset="test-hard"`、循环里 `seed, tier = env_builder.resolve_episode(episode)`、`make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])`）——3 行替换 + 1 行插入，diff 计 3 条 `<` 与 4 条 `>`，共 7；计划的 8 是算错。判定按「只差这 4 处」成立，判定行写实测值。
- **零命中闸门**：计划原命令 `git grep -n 'v4_specs\|v4_rollout\|v5_generation\|scripts.eval' -- scripts src tests` 实测 73 处，按原判据是 FAIL，如实记录。逐类：① `scripts/README.md`、`scripts/parity/README.md` 的旧命令说明（阶段 5 重写）；② 正则 `scripts.eval` 的 `.` 匹配任意字符，命中合法的 `scripts/evaluation*.py`；③ 计划要求保留的方法名 `from_v4_specs`；④ 迁移脚本按固定提交 `git show 55f1b027:scripts/parity/v4_specs.py`／`…:scripts/eval/v4_eval.py` 读历史原文（`SPECS_IDENTITY`、`TIER_MAX_STEPS_SOURCE` 的真源）；⑤ `src/robomme/env_record_wrapper/episode_config_resolver.py`（阶段 3 回退后消失）；⑥ 注释与 docstring 里的历史说明。严格版（真正会坏的引用）：`git grep -nE '^\s*(from|import)\s+\S*(v4_specs|v4_rollout|v5_generation|scripts\.eval\b|legacy_keep_list)' -- scripts src tests` = 0，`importlib` 字符串导入 = 0。阶段 5 重写两份 README 后复跑原命令。
- **核心短测**：`4 failed, 1175 passed, 4 skipped`（181.8 s），4 个失败即开工前就有的 4 个（`test_TaskGoal.py` 恢复官方原文后仍失败的两例对应当前改过的 `src/robomme` task_goal，阶段 3 回退后复核）。

## 三、计划到实施的意外

1. 计划写的 `site/_io.py` 与 Python 内建模块 `_io` 重名，导入必然失败；改名 `site/site_io.py`。
2. 旧 `v6_candidate_values` 的 `_check_sources` 比对当前 `src/robomme/robomme_env` 源码指纹，拆包后不再成立；改为各档草稿来源指纹一致性检查（反例测试仍能抓出篡改）。
3. `ROLLBACK_WRITE` 计划只许 1 局，而冒烟 jsonl 两个任务各选 1 局；continue 模式加 `--tasks` 过滤。
4. 官方 `_worker` 要求局目录不存在：基础设施失败重跑前把旧局目录改名挪开留证（不删）。
5. 删 `test_v6_swap_uniform.py` 一个用例时连带删掉了下一个用例的 `parametrize` 装饰器，核心短测报 fixture 错误后从 git 取回原装饰器。
6. 用 `robomme_hard` 重新抽出的 BinFill／PickXtimes xhard1 候选 0 规格哈希与包内迁移规格逐位相同（抽签可复现的旁证）。

## 四、预算计数

本阶段 reset 2（FREEZE_ONLY_JSONL），rollout 4（ROLLBACK_WRITE 1 + NATIVE_SMOKE 2 + HARD_EVAL_SMOKE 1）。累计：rollout 4／638；纯 reset 3 + rollout 各 1 = 7／715。

## 附：阶段 5 重写两份 README 后复跑零命中闸门（2026-09-28）

原命令 `git grep -n 'v4_specs\|v4_rollout\|v5_generation\|scripts.eval' -- scripts src tests` 由 73 处降到 41 处，逐文件：injection-dev 各模块 docstring 的来历说明（`_draw`、`_freeze`、`_report`、`_rollout`、`site_io` 各 1）、`migrate_smvla_specs.py` 7（按固定提交 `git show` 历史原文 + 说明）、`site/v6_tier_monotone.py` 8（CLI 文案与被测试断言的 `sample_source` 字符串）、`hard_regression.py` 1（正则误中 `scripts/evaluation_hard.py`）、两份 README 共 5（历史说明）、`hard_builder.py` 1（保留的方法名 `from_v4_specs`）、`hard_specs.py` 2（来历说明）、tests 12（测试名、注释、正则误中 `scripts/evaluation.py`）。按原判据仍记 FAIL；严格版（导入已删模块）= 0。
