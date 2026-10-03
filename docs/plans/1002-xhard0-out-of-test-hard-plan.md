# 1002 xhard0 退出 test-hard：builder 只发 V9 的 50 局（开关可逆、源码保留）

> 只规划不实施，获批后执行。锚点 `569c1442`（12.340，已同树合入 main `95006e15`），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，工作区 clean（他人在途 `?? runs/`、` m third_party/SimpleMemVLA` 不碰）。commit 接 12.341。用户原话（2026-10-02）：「给出方案，现在的 xhard0 不要放在这个 test-hard 里面。readme 也对应删除。不要删除源代码，以后可能还要恢复。」

# 第一部分（给人看）

## 一、总览

**一句话方案**：在 `hard_specs.py` 加一个开关 `XHARD0_IN_TEST_HARD`（默认关，环境变量 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` 可临时打开），builder 在 `test-hard` 下不再前置官方 hard 的 12 局；`get_episode_num()` 每任务恰 50、16 任务共 800；xhard0 相关函数、常量、清单、对拍子命令全部保留，依赖「前 12 局是 xhard0」的三处脚本改为跟随开关或在开关关闭时明确报错；测试按开关参数化；README 删掉 xhard0 在 test-hard 里的叙述。

**已定口径**：
1. `get_episode_num()` = 50，`evaluation_hard.py` 循环恰 16 × 50 = 800 局（此前「保留 xhard0 但不计入 800」作废）。
2. 不删任何源码：`_xhard0_entries`、`XHARD0_*` 常量、`TIER_MAX_STEPS["xhard0"]`、`configs/newtask-v7/xhard0_manifest.json`、`xhard0-reset-parity`／`xhard0-eval-parity` 子命令原样保留。
3. 恢复路径：`ROBOMME_HARD_XHARD0_IN_TEST_HARD=1`（或把常量改回 True）即回到 62 局；不需要回滚提交。
4. `max_steps=1600` 入口不动；`TIER_MAX_STEPS` 不动（B5 仍待定）。
5. 不跑核心短测（用户指示）；只跑定向测试与秒级守卫。

## 二、机制：开关在哪、谁会因此错位

**builder**（`src/robomme_hard/env_record_wrapper/hard_builder.py::BenchmarkEnvBuilder.__init__` test-hard 分支）现在是 `xhard0 = _xhard0_entries(env_id, self.metadata_index)` → `_test_hard_entries(env_id, xhard0, root)` 以 `entries = list(xhard0)` 开头再追加 xhard1～5。改为 `xhard0 = _xhard0_entries(...) if hard_specs.XHARD0_IN_TEST_HARD else []`（以模块属性方式读，monkeypatch 与环境变量才生效）。`resolve_episode`／`resolve_identity`／`_hard_env_kwargs` 对 xhard0 的分支按 tier 判断，条目为空自然不触发，不改。

**开关**（`hard_specs.py`，紧挨 `XHARD0_PER_TASK`）：`XHARD0_IN_TEST_HARD: bool = os.environ.get("ROBOMME_HARD_XHARD0_IN_TEST_HARD", "0") == "1"`，并提供 `xhard0_prefix() -> int`（开则 12、关则 0）供脚本取偏移。`BUILDER_TIERS`、`TIER_MAX_STEPS` 不动（模块级 assert 绑定两者）。

**会静默错位的三处脚本**（盘点结论，必须跟进）：
- `scripts/parity/hard_regression.py`：`delivery_index` 把交付行映射到 `builder_episode` 时写死 `+ XHARD0_PER_TASK`；`expected_episodes` 每任务局数写死 `12 +`。改为 `+ hard_specs.xhard0_prefix()`。`eval-smoke`／`reset-replay` 随之正确；`xhard0-reset-parity` 的 H 侧把 builder episode 0..11 当 xhard0，开关关闭时在入口直接 `SystemExit("需 ROBOMME_HARD_XHARD0_IN_TEST_HARD=1")`。
- `scripts/parity/train_split_worker.py` 的 `--builder-route test-hard` 在 builder 里找唯一 xhard0 条目：开关关闭时同样明确报错（不改逻辑）。
- `scripts/injection-dev/export_eval_identities.py`：`XHARD0_TOTAL=192`、`expected_total=992`、默认文件名 `eval-identities-992.jsonl` 写死；改为按开关取 0/192、800/992、文件名用实际总数。开关关闭时导出 800 行 `eval-identities-800.jsonl`。

**不受影响、不改**：`hard_parity.py`（独立读官方 test 元数据与 manifest）、`v8_manifest.py`／`env_client.py` v8 模式（按行 tier 查表）、`step-headroom --xhard0`（读 h5）、`v8_site_catalog.py`（读身份文件；已有 992 文件照旧）、已跑的 V9 评估产物（基于 992 口径，历史留档不动）。

## 三、验收

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| builder 每任务 50、共 800、档位只含 xhard1～5 且单调 | `tests/lightweight/test_v9_packaged_800.py`（改为开关关闭口径） | `V9_PACKAGED=PASS total=800 per_task=50 cells=43 episodes_per_task=50 xhard0_in_test_hard=False` |
| 开关打开仍是 62/992 | `test_hard_builder_xhard0.py` 参数化 `[False, True]`（monkeypatch 模块属性；builder fixture 按开关各建一份） | 两档都 passed |
| 偏移跟随开关 | `test_v8_regression_cmds.py::test_reset_replay在v8根按V8_TIERS读` 参数化：关时 `min(builder_episode)==0`，开时 12 | passed |
| 导出口径 | `test_v8_delivery_flow.py::test_export_eval_identities的1262口径` 补关闭档：`expected_total==800`、文件名 `eval-identities-800.jsonl` | passed |
| 入口实跑 | `ROBOMME_ENV_PACKAGE=robomme_hard` 下只构建 builder 不起仿真：16 任务 `get_episode_num()` 之和 | 800（测试内已覆盖；另用上一轮 `truncate_probe.py` 跑 BinFill episode 0 一局确认 `tier=xhard1`、`episode_num=50`、第 1601 步截断，GPU，1 次 reset） |
| 守卫 | `UPSTREAM_GUARD`、四入口、录像器零 diff、`git diff --check` | PASS |

## 四、README 删改（对应删除 xhard0 叙述）

- `scripts/README.md` §1：入口改为「跑 V9 五档（xhard1～xhard5）」；「换数据集」改「`test-hard` 每任务 50 局，按 xhard1 到 xhard5 依次排列，16 任务合计 800 局」；删 xhard0 一句；「场景从哪里来」删首段 xhard0；「构造 builder 时它先排 xhard0」改为直接读五份文件。§3 配置表 xhard0 列改名「官方 hard（参考）」并加一句「官方 hard 不在 `test-hard` 里；需要对照时 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` 可前置 12 局」；局数表删「xhard0 另有 192」句；步数上限句删 `xhard0 最大 1074`。§5 `xhard0-reset-parity` 命令旁注「需开关打开」。§6 核查行注释改「800 局 / 50 局 / 固定 1600 / 3 行 diff」。
- `src/robomme_hard/README.md`：标题「六档」→「五档（xhard1～xhard5；xhard0 官方 hard 可选前置）」；① 节局数句改 50/800 并写开关；⑤ 节「每任务 62 局（12 + 50）」改 50、`resolve_identity` 的 xhard0 说明加「仅开关打开时」。

## 五、子代理分工与合并（简述）

拆两块、互不重叠：S1 包与 builder 测试（`hard_specs.py`、`hard_builder.py`、`test_hard_builder_xhard0.py`、`test_v9_packaged_800.py`）；S2 脚本与脚本测试（`hard_regression.py`、`train_split_worker.py`、`export_eval_identities.py`、`test_v8_regression_cmds.py`、`test_v8_delivery_flow.py`）。S2 只依赖 S1 的接口契约（常量名 `XHARD0_IN_TEST_HARD`、函数 `xhard0_prefix()`），两块并行派发；两份 README 主会话自改。合并顺序 S1 → S2，每块合并前一个 sonnet 只读审查、合并后跑该块定向测试与守卫；最后主会话改 README、跑一局 GPU 探针、commit 12.341、push。

## 六、实施步骤表

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 派发前核对：`worktree.baseRef=head`、主检出 clean（忽略 `runs/`、子模块）、`BASE=569c1442` | 四项 OK |
| 1 | 并行派 S1、S2（opus，worktree） | 各自定向测试 passed、交回清单 |
| 2 | S1 合并前审查 → `--no-ff` 合入 → 跑 `test_hard_builder_xhard0.py test_v9_packaged_800.py test_xhard0_native.py` | `PRE_MERGE_REVIEW=PASS`、`POST_MERGE_REVIEW=PASS` |
| 3 | S2 同上 → 跑 `test_v8_regression_cmds.py test_v8_delivery_flow.py` | 同上 |
| 4 | 主会话改两份 README；GPU 探针 1 局（`tier=xhard1 episode_num=50 steps=1601 truncated=True`）；守卫 | 判定行如 §三 |
| 5 | 留档追加到 `docs/validation/newtask-v9/cleanup-20261002.md` 五″节；`docs/1002-pending-decisions.md` 记「xhard0 退出 test-hard，开关可恢复」；commit 12.341、push；清理两个 worktree | `git status -sb` 无 ahead |

# 第二部分（技术细节，供 agent 追踪）

## 〇 红线

- R1 不删任何函数、常量、文件；`src/robomme/` 零 diff；`BUILDER_TIERS`、`TIER_MAX_STEPS` 不动。
- R2 开关以模块属性读取（`hard_specs.XHARD0_IN_TEST_HARD`），禁止 `from hard_specs import XHARD0_IN_TEST_HARD` 成局部名。
- R3 开关关闭时，凡逻辑上必须有 xhard0 的入口（`xhard0-reset-parity` H 侧、`train_split_worker --builder-route test-hard`）一律显式 `SystemExit`，不许静默跳过或错位。
- R4 不跑核心短测；GPU 探针只 1 局（reset 预算 1）。
- R5 `artifacts/` 不动；已有 `eval-identities-992.jsonl` 等产物不重导。

## 一 逐文件改动清单

1. `src/robomme_hard/env_record_wrapper/hard_specs.py`：顶部 `import` 区加 `import os`（现无）；`XHARD0_PER_TASK` 下方加
   ```python
   #: xhard0（官方 hard 12 局）是否前置在 test-hard 里。V9 定稿默认关（每任务恰 50 局、16 任务 800 局）；
   #: 设 ROBOMME_HARD_XHARD0_IN_TEST_HARD=1 可恢复为 12 + 50（源码与清单全部保留）。
   XHARD0_IN_TEST_HARD: bool = os.environ.get("ROBOMME_HARD_XHARD0_IN_TEST_HARD", "0") == "1"
   def xhard0_prefix() -> int:
       """test-hard 里排在新值档前面的 xhard0 局数：开关开为 XHARD0_PER_TASK，关为 0。"""
       return XHARD0_PER_TASK if XHARD0_IN_TEST_HARD else 0
   ```
   模块 docstring 加一句。
2. `src/robomme_hard/env_record_wrapper/hard_builder.py`：`__init__` test-hard 分支 `xhard0 = _xhard0_entries(env_id, self.metadata_index) if hard_specs.XHARD0_IN_TEST_HARD else []`；模块 docstring「xhard0 12 局在前」改为「开关打开时在前，默认关」。`_test_hard_entries` 不改。
3. `scripts/parity/hard_regression.py`：`delivery_index` 与 `expected_episodes` 的 `XHARD0_PER_TASK` 偏移改 `hs.xhard0_prefix()`；`cmd_xhard0_reset_parity` 入口与 `eval-smoke` 中用到「episode 0..11 为 xhard0」的分支加开关检查 `SystemExit`。
4. `scripts/parity/train_split_worker.py`：`--builder-route test-hard` 找 xhard0 条目处，找不到时的错误信息加「ROBOMME_HARD_XHARD0_IN_TEST_HARD=1」提示（逻辑不变）。
5. `scripts/injection-dev/export_eval_identities.py`：`XHARD0_TOTAL = 16 * hs.xhard0_prefix()`；`expected_total(cells) = sum(cells) + XHARD0_TOTAL`；默认输出名 `identities_name(total)` 用实际总数；`--official-out` 在开关关闭时跳过并打印 `official=skipped`。
6. 测试：`test_hard_builder_xhard0.py`（fixture 改为按开关参数化构建；62/992 断言在 True 档、50/800 在 False 档；`resolve_identity(12)` → 按偏移取）；`test_v9_packaged_800.py`（builder 用例改 50/800、档位序列不含 xhard0，打印 `xhard0_in_test_hard=False`；另加 True 档 monkeypatch 一条 62）；`test_v8_regression_cmds.py::test_reset_replay在v8根按V8_TIERS读`、`test_eval_smoke每任务局数按格表推出` 参数化偏移；`test_v8_delivery_flow.py::test_export_eval_identities的1262口径` 加 False 档 800。
7. README 两份：按第一部分 §四。
8. 留档：`docs/validation/newtask-v9/cleanup-20261002.md` 五″节（原话、改法、判定行、探针行）；`docs/1002-pending-decisions.md` 总表加一行「xhard0 已退出 test-hard（开关），xhard0 评估/对拍设施保留」。

## 二 子代理分配表

| 编号 | 目标 | 可写集合 | 禁触 | 接口契约 | 验收（worktree 内，`UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<wt>/src uv run --no-sync`，先打印 `robomme_hard.__file__` 以 `<wt>/src/` 开头） | 合并顺序 |
|---|---|---|---|---|---|---|
| S1 | 开关 + builder + 包测试 | `src/robomme_hard/env_record_wrapper/hard_specs.py`、`hard_builder.py`、`tests/lightweight/test_hard_builder_xhard0.py`、`tests/lightweight/test_v9_packaged_800.py` | 其余一切；`src/robomme/` | 提供 `hard_specs.XHARD0_IN_TEST_HARD`（bool，env 可覆盖）与 `hard_specs.xhard0_prefix()`；`BUILDER_TIERS`/`TIER_MAX_STEPS` 不变 | `python -m pytest tests/lightweight/test_hard_builder_xhard0.py tests/lightweight/test_v9_packaged_800.py tests/lightweight/test_xhard0_native.py -q -s` 全 passed，末行含 `V9_PACKAGED=PASS … episodes_per_task=50 xhard0_in_test_hard=False`；`ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` 再跑一次同样 passed | 1 |
| S2 | 脚本偏移跟随开关 + 脚本测试 | `scripts/parity/hard_regression.py`、`scripts/parity/train_split_worker.py`、`scripts/injection-dev/export_eval_identities.py`、`tests/lightweight/test_v8_regression_cmds.py`、`tests/lightweight/test_v8_delivery_flow.py` | 其余一切 | 只调用 S1 契约里的两个名字（S2 的 worktree 基于 BASE，没有 S1 改动：先在本地以 `getattr(hs, "xhard0_prefix", lambda: hs.XHARD0_PER_TASK)()` 形式兼容，合并后由主会话确认） | `python -m pytest tests/lightweight/test_v8_regression_cmds.py tests/lightweight/test_v8_delivery_flow.py -q` 全 passed（基线：这两文件在 BASE 全 passed） | 2 |
| 主会话 | README 两份、留档、待定清单、GPU 探针、commit | `scripts/README.md`、`src/robomme_hard/README.md`、`docs/validation/newtask-v9/cleanup-20261002.md`、`docs/1002-pending-decisions.md` | — | — | 守卫四项 + 探针行 | 3 |

资源：S1/S2 纯 CPU；探针 GPU 1 张、1 次 reset。共享文件：无。`sub/S1: `、`sub/S2: ` 前缀 commit，`--no-ff` 合入，合并前后各一次审查。

## 三 闸门总表

`V9_PACKAGED`（50/800）、S1 两档测试、S2 两文件测试、`TRUNCATE_PROBE … tier=xhard1 episode_num=50 steps=1601 truncated=True`、`UPSTREAM_GUARD=PASS`、四入口、录像器零 diff、`git diff --check`。

## 四 runbook

```bash
# 派发前
grep baseRef ~/.claude/settings.json; git status --short --ignore-submodules=dirty; git check-ignore -q .claude/worktrees/probe && echo ok; git worktree list
# 合并（每块）
git diff --name-only <BASE>..<TIP>      # ⊆ 可写集合
git merge --no-ff <TIP> -F <说明>
# 探针（合并后）
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python <scratchpad>/truncate_probe.py BinFill 0   # → tier=xhard1 episode_num=50 steps=1601
```

## 五 风险

- S2 基于 BASE 看不到 S1 的新函数：用 `getattr` 兼容写法，合并后主会话 grep 确认已改为直接调用。
- `hard_fingerprint` 告警：改 `src/robomme_hard` 任何 `.py` 都会让包内规格 header 指纹不符（只告警）；现状已如此，本轮不处理。
- `evaluation_hard.py` 不改：`max_steps=1600` 与 50 局循环天然成立。
- 已有 V9 评估清单（992 身份）与站点目录继续按历史口径工作；以后再导出身份时得到 800 行、文件名随总数。

## 六 盲区

- `hard_regression.py` 里是否还有第三处隐含「前 12 局」假设（如 `eval-smoke` 的 `--episode` 语义文档），S2 实施时 grep `XHARD0_PER_TASK|xhard0` 逐处核对并在交回清单列明。
- `v8_site_catalog.py` 自带 `XHARD0_PER_TASK=12` 常量，读 800 行身份文件时会报 `x0_per_task` 不符；本轮不重导身份文件故不触发，记入待定清单。

## 七 留档与 commit

commit `12.341 xhard0 退出 test-hard：开关 XHARD0_IN_TEST_HARD 默认关、builder 每任务 50 局、脚本偏移跟随开关、README 删 xhard0 叙述`，body 六项（用户原话、计划、实施、意外、测试判定行、下一步），push。
