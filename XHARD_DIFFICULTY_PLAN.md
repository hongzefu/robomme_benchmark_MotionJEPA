# xhard 难度扩展计划：VideoRepick／VideoUnmaskSwap swap 4～5 次、RouteStick 8～10 段

> **边界**：只规划、不实施；实施时每一步须单独获批，其中 `src/robomme/` 的 8 处改动须用户逐条批准（AGENTS.md 规则 11）。
> **代码锚点**：分支 `newtask-v2`，commit `379b8ed`（10.56），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。commit 编号从 `10.57` 起接续。
> **外部锚点**：已冻结运行 `artifacts/injection/20260911-contract-v2-05/`（契约 v2，11 组 × 100 条，实跑 330 条）。
> **落档**：实施第一步把本文落为仓库根 `XHARD_DIFFICULTY_PLAN.md`，实测结果以子节追加。

**用户原话（逐字）**：

> 给出方案 给videorepick和videpunmaskswap加入swap 4-5次 作为xhard难度模式
>
> 其他和videorepick medium videpunmaskswap hard保持一致
>
> 给routestick增加xhard模式 和hard保持一致 但是走的段数增加8-10

追问答复（2026-09-11）：RouteStick 段数「落在 8～10」；第 4、5 次发起者「循环沿用 3 个发起者」；「契约 v3 + 新 run 只跑 3 个 xhard 组」。

---

# 第一部分（给人看）

## 要做的事其实就三件

1. **让环境认识 xhard。** 现在每个任务里有三份小字典 `config_easy / config_medium / config_hard`，写着「swap 几次」「走几段」这些数字。给三个任务各加一份 `config_xhard`：
   - RouteStick：段数 8～10，允许回退（其余照抄 hard）
   - VideoUnmaskSwap：swap 4～5 次（其余照抄 hard：4 个容器、抓 2 次）
   - VideoRepick：swap 4～5 次（其余照抄 medium：3 块方块）

   另外有个「合法难度名单」只认 easy/medium/hard，要把 xhard 加进去。

2. **让 swap 能做到第 4、5 次。** 现在代码写死了「最多 3 次 swap」：时间表只有 1/2/3 次三种写法，发起者也只有 3 个槽位。要改成「有几次就排几段，每段 50 帧接着排」。第 4、5 次谁来发起？你已选「循环用原来那 3 个」，即顺序是 a、b、c、a、b。这样相邻两次发起者不同，不会出现「同一块自己换回去」的废事件。

3. **按原有流程生成规格、跑仿真、出图。** 这条流水线是「契约 JSON 定取值范围 → 冻结 100 条规格/组 → 实跑前 30 条 → 出数轴图」。做法是：契约出 v3（= v2 加 3 个 xhard 组，旧 11 组一字不动），新建一次运行冻结 14 组，但只实跑 3 个 xhard 组 × 30 = 90 条，数轴图上补 3 组变 14 组。

## 具体实现方式

### `src/robomme` 的 8 处小改动（逐条报批）

| # | 文件 | 改什么 | 为什么 |
|---|---|---|---|
| S1 | `src/robomme/robomme_env/utils/difficulty.py` | `VALID_DIFFICULTIES = {"easy", "medium", "hard"}` 加 `"xhard"` | 不加，传 `difficulty="xhard"` 直接报 `ValueError`，进不了门 |
| S2 | `src/robomme/robomme_env/RouteStick.py` | 类属性加 `config_xhard = {'length': [8, 10], 'backtrack': True}`，并加进 `configs` 字典 | 事 1；`_load_scene` 按键查字典，不用再改 |
| S3 | `src/robomme/robomme_env/VideoUnmaskSwap.py` | 类属性加 `config_xhard = {"bin": 4, "swap_min": 4, "swap_max": 5, "pick_min": 2, "pick_max": 2}`，并加进 `configs` | 事 1 |
| S4 | 同上，`_load_scene` | 在 `self.swap_pair3_idx2=None` 之后、`self._refresh_swap_schedule()` 之前追加：`for k in range(3, self.swap_times): setattr(self, f"swap_pair{k+1}_idx1", self.spawned_bins[swap_indices[k % 3]]); setattr(self, f"swap_pair{k+1}_idx2", None)` | 事 2 的发起者循环；swap ≤ 3 次时这个循环一次都不跑，旧行为一字不变 |
| S5 | 同上，`_refresh_swap_schedule` | 三个 `if swap_times==1/2/3` 分支换成通式：`swap_times < 1` 时不赋值；否则 `swap_schedule = [(第 k+1 对发起者, 第 k+1 对搭档, 64 + 50k, 64 + 50(k+1)) for k in range(swap_times)]` | 事 2 的时间表；1/2/3 次时算出的元组与原分支逐项相同 |
| S6 | `src/robomme/robomme_env/VideoRepick.py` | 类属性加 `config_xhard = {"cube": 3, "swap_min": 4, "swap_max": 5}`，并加进 `configs` | 事 1 |
| S7 | 同上，`_load_scene` 的 `if self.difficulty != "hard":` 分支 | 同 S4，对象用 `self.spawned_cubes[swap_indices[k % 3]]` | 事 2 |
| S8 | 同上，`_refresh_swap_schedule(self, start_step=400)` | 同 S5，起点用 `start_step`（由 `step()` 在关节静止时闩锁） | 事 2 |

不动的：每个环境 `__init__` 里 `seed % 3` 的兜底分支（xhard 只能显式传）、`step()`（已经按 `len(swap_schedule)` 循环）、`_verify_swap_binding` 等注入核验（按段号查规格，段数多了自动多查几次）、录像器。

### scripts 侧要跟着改的

- **原值快照** `scripts/configs/newtask-v2/native_sampling.json`：它是从源码 AST 提取的，提取器写死了三个键，改成「有 `config_xhard` 才写 `xhard`」，然后用 `--extract-config` 重新导出（BinFill 仍是三键）。
- **取值域散列前置修复**：散列现在算整份 `configs`，加一键就变，会让 05 的 `check` 拒绝复验、v1/v2 契约的逐字节测试变红。改成只算「本次用到的难度」，三档算出来仍是冻结时的 `124e49f8…`（已数值验证），05 与 v1/v2 都不受影响。固定基线操作元路径 `parameters.<任务>.configs` 同理拆成按难度三条。
- **规格生成器** `scripts/injection/specs.py`：发起者序列从 `initiators_full[:n]` 改成 `[initiators_full[k % 3] for k in range(n)]`（n ≤ 3 时完全一样）；加 `XHARD_GROUPS`、`GROUPS_V3`，原 `GROUPS` 保持 11 组。
- **契约** `scripts/injection/contract_build.py`：加 `build-v3`，= v2 深拷贝 + 三个 xhard 组，v1/v2 文件一字不动。
- **编排** `scripts/injection/campaign.py`：`plan` 的组列表改从契约取、`check` 从清单取（否则 14 组只查 11 组）；静态检查加「第 k 段发起者 = 循环基的第 k mod 3 个」；`run` 加 `--groups` 只跑三个 xhard 组；跑后图的箭头透明度不再在第 5 次归零。
- **可视化** `scripts/injection-before-2d/`：swap 颜色 3 → 5 色，事件面板「①全部 + 第 1..K 次」，数轴脚本合并 05（旧 11 组）与 06（3 个 xhard 组）两次实跑，产物计数按组数算。
- **测试**：改枚举断言，新增「调度通式与旧三分支逐项相等」「发起者循环」「散列作用域」三条单测。
- **文档**：契约变更日志加 v3 节、流水线文档与 README 加 xhard、AGENTS 账本。

### 怎么保证没弄坏旧的三档

1. 新单测：通式在 1/2/3 次时与旧分支逐项相等。
2. 用 05 的规格各任务跑 1 条（4 条），HDF5 与 05 逐位对拍。
3. 新运行里旧 11 组的 1100 条规格散列与 05 逐条相同。
4. 05 的 `campaign check` 改完后重跑必须过。
5. `tests/lightweight` 全量（约 3 分钟，4 条既有失败与本轮无关）。

### 分几步做

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 落计划到仓库；跑现状基线 | 05 `CHECK=PASS`、轻量测试 |
| 1 | 脚本侧前置：散列作用域、操作元路径、组列表真源、提取器可选四键 | 05 仍 `CHECK=PASS`，轻量测试全绿 |
| 2 | 逐条报批 S1～S8 并落地；重导快照；新单测；4 条对拍 | `OLD_TIER_PARITY=PASS compared=4 differences=0` |
| 3 | 契约 v3、发起者循环、`--groups` | `CONTRACT_DERIVED=PASS version=v3`、v1/v2 零改动 |
| 4 | 冻结并检查 `20260911-contract-v3-06` | `PLAN=OK groups=14 specs=1400`、`CHECK=PASS`、旧组 `compared=1100 differences=0` |
| 5 | xhard 冒烟 3 条 → 实跑 90 条 | `FEASIBILITY=PASS unique=90`、`RUN=PASS` |
| 6 | 出图与两份 md | 14 组齐、旧组表零漂移、xhard 数轴 swap 4～5 条、RouteStick T 在 800～1000 |
| 7 | 文档与账本，逐笔 commit + push | `git status -sb` 无 ahead |

---

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 `src/robomme/` 只改 S1～S8，逐条获批后才动；同文件未点名处、「顺手修」都不算获准。`RecordWrapper.py` 冻结，`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 必须为真。
- R2 三档随机流、规格 `spec_sha256`、HDF5 逐位不变是总闸门；任何一步破坏它即停。
- R3 `seed % 3` 兜底、RouteStick 兜底分支末尾的 `self.difficulty = "easy"` 旧行、`swap_selection`／`object_selection` 锁死块、`_injection_evidence` 三槽位一律不动。
- R4 `injection_contract_v1.json`／`v2.json`、`artifacts/injection/20260910-new-values-04/`、`20260911-contract-v2-05/`、`docs/validation/newtask-v2/`（带 sha 锁的交付证据）全部只读。
- R5 冻结失败（候选耗尽）、实跑失败率异常时不放宽判据、不改规格、不改几何常量，报缺口交用户。
- R6 超 5 分钟的阶段用 detached tmux + Monitor；一切 Python 用 `uv run --no-sync`。
- R7 commit 只 `git add` 本轮点名路径；每笔 commit 后立即 `git push`；提交前 `git status --short` 核对。

## 一、口径与机制细节

1. **难度进入路径**：`scripts/generate_dataset_newseed.py` 建环境时 `kwargs["difficulty"] = job.difficulty`；清单模式下来自清单每组 `difficulty` 字段（`load_episode_specs` → `SpecGroup.difficulty`），与 `--difficulty` 循环比例无关。`seed_layout.py::DIFFICULTY_ORDER`／`parse_difficulty_ratio`／默认 `"211"` 不改，xhard 不进随机路径的配额循环。
2. **白名单全局**：`VALID_DIFFICULTIES` 被 16 个任务共享，其余 13 个任务被误传 `xhard` 会在 `self.configs[self.difficulty]` 处 `KeyError`（显式失败），在 `difficulty.py` 加注释说明。
3. **调度通式**：

```python
def _refresh_swap_schedule(self, start_step=400):          # VideoUnmaskSwap 无参数，base 固定 64
    if self.swap_times < 1:                                 # 原三分支在 n=0 时不赋值，保持不赋值
        return
    self.swap_schedule = [
        (getattr(self, f"swap_pair{k + 1}_idx1"), getattr(self, f"swap_pair{k + 1}_idx2"),
         start_step + 50 * k, start_step + 50 * (k + 1))
        for k in range(self.swap_times)
    ]
```

   原文 `start_step + 50 * 2`、`64+ 50 * 3` 均为整数常量，通式给出同值，长度、顺序相同。VideoRepick hard（`swap_times=0`）本就不进 swap 分支。S4/S7 必须放在 `_refresh_swap_schedule()` 调用之前（通式会 `getattr` 第 4/5 对）。Unmask 的 `swap_indices` 是 `torch.Tensor`，`spawned_bins[swap_indices[k % 3]]` 与既有写法同形。
4. **时间轴（Unmask n=5）**：`[64,114],[114,164],[164,214],[214,264],[264,314]`；`static_check(static_steps=self.swap_schedule[-1][3])` 与 `lift_and_drop_objectA_onto_objectB(end_step=…)` 自动延到 314；VideoRepick 从 `S+150` 延到 `S+250`。`RecordWrapper::fail_safe_limit = 2000` 远未触及。
5. **`_injection_evidence["swap_initiators"]` 保持 3 个**：消费链 `generate_dataset_newseed`（存结果行）→ `run.py::read_result_rows`（`injection_bound = bool(...)`）→ `INJECTION_BINDING` 只看非空；VideoRepick 的证据本就不含该字段。逐段核对由 `_verify_swap_binding(sweep_index, …)` 对 `actions.swap_pairs[k]` 做。
6. **碰撞被拒率证据**：审查 subagent 用 05 冻结布局离线跑循环发起者模拟（`bin_collision.check_swap_sweep` 原函数）：VideoRepick/medium n=3/4/5 各 100/100 通过、VideoRepick/easy n=5 100/100、VideoUnmaskSwap/hard n=3/4/5 各 100/100，第 4、5 段零被拒；xhard 自身分层流不同，以 `plan_stats.json::max_candidates_used` 复核。
7. **取值域散列作用域**：`specs.py::operand_sha256(sampling, difficulties=None)`，非空时 `parameters.<任务>.configs` 只保留这些键，`positions` 不动。`build_v1/v2` 传 `{d for _, d in GROUPS}`，`build_v3` 传四档；`cmd_plan` 传本次组列表难度集合；`cmd_check` 传 `{item["difficulty"] for item in manifest["groups"]}`。已验证：新源码过滤三档 = `124e49f8…`（与 05 清单、v1/v2 契约冻结值逐位相同）。
8. **基线操作元**：`generate_dataset_newseed.py::SAMPLING_OPERAND_PATHS` 三任务的 `parameters.<任务>.configs` 拆成 `.easy/.medium/.hard` 三条（`_pick_path` 支持点号嵌套），BinFill 保持整块；`--check-config --source-ref 94449db` 才能通过。
9. **契约 v3**：

```python
XHARD_GROUPS = (("RouteStick", "xhard"), ("VideoUnmaskSwap", "xhard"), ("VideoRepick", "xhard"))
GROUPS_V3 = GROUPS + XHARD_GROUPS

def build_v3(base_v2, sampling):
    doc = copy.deepcopy(base_v2); doc["contract_version"] = "v3"
    doc["contract_note"] += "；v3 = v2 + RouteStick/VideoUnmaskSwap/VideoRepick 各加 xhard 组（2026-09-11 用户决定）"
    doc["derives_from_operands_sha256"] = operand_sha256(sampling, {d for _, d in GROUPS_V3})
    doc["added_groups_v3"] = [list(g) for g in XHARD_GROUPS]
    for task, difficulty in XHARD_GROUPS:
        doc["groups"][f"{task}/{difficulty}"] = BUILDERS[task](sampling, difficulty)
    return doc
```

   三个新组零新 recipe：RouteStick `L` → `[8,9,10]` 配额 34/33/33，`edge.backtrack=true`；Unmask `n_swaps` → `[4,5]` 配额 50/50、`n_picks` → `[2]`、`layout_type` 常量 region4；Repick `n_swaps` → `[4,5]`，`tail`／`target`／`layout_type` 复用。`swap_pairs_field(difficulty)` 在 xhard 时把 `expr`／`domain_text` 加注循环规则，v1/v2 文案不变；不新增契约字段。CLI `build-v3 --base --sampling --out`，`--base` 须 v2。
10. **组列表真源**：`cmd_plan` 用 `[(g.task, g.difficulty) for g in contract.groups()]`（`Contract.groups()` 已存在）；`_check_reproducible` 用 `reversed(list(documents))`；`_check_scope` 的 `excluded` 由 `EXCLUDED_GROUPS` 拼接；`_static_problems` 视频分支加 `swaps[k]["initiator"] == objects["swap_initiators"][k % 3]`（旧组恒成立）。`_repick_group` 的 `if difficulty == "hard": raise` 保留；`contract.py`、`categories.py` 不改。
11. **实跑编排**：`run` 加 `--groups`（逗号分隔 `任务/难度`，默认清单全部；未知键 `CampaignError`）；清单名 `feasibility{len(groups)*30}.json`（06 得 `feasibility90.json`，05 的 `feasibility330.json` 不动）；note、print、`cmd_report` 标题按实际条数；`COLLISION_RUNTIME` 注释改「本次实跑里的视频任务组」；`plots.py` 箭头 `alpha = max(0.2, 0.8 - 0.15 * order)`。`run.py::CALIBRATION_GROUPS`、`tests/_shared/parallel_calibration.py::TASKS` 不动（本轮 `--tier 20` 跳过校准），注释补一句。
12. **可视化**：`plot_injection_before_2d.py::SWAP_COLORS` 加 2 色（如 `#ad1457`、`#5d4037`，前 3 色不动）；事件面板 `make_panels(1 + K, 4 if K == 3 else 3)`，K = max(3, 该组最大 n_swaps)，`counts = [0] * (1 + K)`，圈号 `'②③④⑤⑥'[k]`，图例 `range(K)`；`GROUPS` 五份副本收敛：`specs.py`、`contract_build.py` 各留常量（11 组 + `GROUPS_V3`），`window_timeline.GROUPS` 改为 14 组，`event_tables.py`、`plot_injection_before_2d.py` 从 `window_timeline` 导入，测试断言 `window_timeline.GROUPS == list(specs.GROUPS_V3)`；`event_tables.DEFAULT_RUN_ID` → 06；`window_timeline.py` 的 `--rollout-run-id` 接受逗号分隔多运行，后者覆盖前者同 key 行，JSON 每组记来源；`plot_sampling_windows.py` 标题、图例 `range(len(SWAP_COLORS))`、判定 `files == len(GROUPS) + 1`；`check_doc_links.py` 两个常量按 `len(GROUPS)`。两份 md 由脚本 `--write` 重生成，`--check` 核表格文本，图字节允许漂（不入库）。
13. **测试改动**：`test_native_sampling_config.py`（三任务四键、BinFill 三键；基线操作元断言不改）、`test_injection_campaign.py`（`len(GROUPS) == 11` 保留，加 `len(GROUPS_V3) == 14`、`--groups` 过滤与未知键报错）、`test_injection_contract.py`（v1/v2 断言不改；加 v3 逐字节、v2→v3 同名组逐字相同且 `added=3`）、`test_episode_action_sampling.py`（参数化加 xhard，对象数 Unmask 4／Repick 3）、`test_episode_specs.py`（n_swaps=4/5 规格通过校验）、`test_window_timeline.py`（5 色、5 段）；新增 `test_swap_schedule_generic.py`（`generator._func_def` 抽 `_refresh_swap_schedule` 在 `SimpleNamespace` 上执行，n=0..5 对照手写期望）、`test_xhard_initiator_cycle.py`、`test_operand_scope.py`。
14. **文档**：`XHARD_DIFFICULTY_PLAN.md`（新）、`scripts/NEW_VALUE_CONTRACT_CHANGELOG.md`（加 v3 节：三组、循环规则、散列作用域与验证数字、「快照与 src 须同版本」、用户原话）、`scripts/NEW_VALUE_INJECTION_PIPELINE.md`（结果速览加 06；复现命令加 `build-v3`、`plan/check 06`、`run --groups`、`window_timeline extract --rollout-run-id 05,06`）、`scripts/README.md` §1.1（加 xhard 三行；`--difficulty` 旁注「xhard 不进配额」）、`NEW_VALUE_INJECTION_TEST_PLAN.md`（追加 xhard 段）、`AGENTS.md` 日志。`artifacts/injection/20260911-contract-v3-06/{specs/,manifest.json,plan_stats.json,check_result.json}` 按现有 `.gitignore` 反选自动入库。

## 二、对拍闸门总表

| 闸门 | 命令（仓库根，`uv run --no-sync`） | 判定行 |
|---|---|---|
| G0/G8 | `python -m scripts.injection.campaign check --run-id 20260911-contract-v2-05`（约 6 分钟，tmux） | `CHECK=PASS` |
| G1 | `tests/lightweight/test_operand_scope.py`：`operand_sha256(snapshot, {"easy","medium","hard"}) == "124e49f8…"` | `SCOPED_SHA=PASS` |
| G3 | `python scripts/generate_dataset_newseed.py --extract-config scripts/configs/newtask-v2/native_sampling.json`；再 `--check-config`；再 `--check-config --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8` | `CONFIG_CHECK=PASS xhard_tasks=3`、`BASELINE_OPERANDS=PASS` |
| G4 | `python -m pytest tests/lightweight/test_swap_schedule_generic.py -q` | `SCHEDULE_EQUIV=PASS n=0..5` |
| G5 | 临时清单（05 的 BinFill/hard、RouteStick/hard、Unmask/hard、Repick/medium 各 ep0）→ `python scripts/generate_dataset_newseed.py --episode-specs <清单> --sampling-config scripts/configs/newtask-v2/native_sampling.json --output-dir artifacts/xhard-smoke/old-tier --workers 1 --gpus 0`（约 8 分钟，tmux）；`python -m scripts.injection.campaign compare --left artifacts/injection/20260911-contract-v2-05/feasibility/P01x20 --right artifacts/xhard-smoke/old-tier --label OLD_TIER_PARITY --subset-only` | `OLD_TIER_PARITY=PASS compared=4 differences=0` |
| G6 | `python -m pytest tests/lightweight -q --durations=5`（约 176 秒） | 通过数 = 总数 − 4（既有失败 `test_TaskGoal.py`×2、`test_step_error_handling.py`×2） |
| G7 | `python -m scripts.injection.contract_build build-v3 --base scripts/configs/newtask-v2/injection_contract_v2.json --out scripts/configs/newtask-v2/injection_contract_v3.json`；`… check --contract …_v3.json`；`git diff --quiet -- scripts/configs/newtask-v2/injection_contract_v1.json scripts/configs/newtask-v2/injection_contract_v2.json`；`python -m scripts.injection.campaign plan --run-id 20260911-contract-v3-06 --contract scripts/configs/newtask-v2/injection_contract_v3.json`；`… check --run-id 20260911-contract-v3-06`（约 10 分钟，tmux）；`… specs-diff --left 20260911-contract-v2-05 --right 20260911-contract-v3-06` | `CONTRACT_DERIVED=PASS version=v3 mismatches=2 overrides=2 problems=0`、`V1_V2_UNCHANGED=PASS`、`PLAN=OK groups=14 specs=1400`、`CHECK=PASS`（含 `SPEC_REPRODUCIBLE compared=1400 differences=0`）、`OLD_GROUPS_EQUIVALENCE=PASS compared=1100 differences=0` |
| G9 | 临时清单（xhard 三组各 ep0，RouteStick 换成一条 L=10）→ 生成器 `--workers 1` | `XHARD_SMOKE=PASS cases=3 binding_mismatch=0` |
| G10 | tmux `inj06-feas`：`python -m scripts.injection.campaign run --run-id 20260911-contract-v3-06 --phase feasibility --tier 20 --gpus 0,1 --groups RouteStick/xhard,VideoUnmaskSwap/xhard,VideoRepick/xhard`；Monitor：`tail -n +1 -F <log> \| stdbuf -oL tr '\r' '\n' \| grep --line-buffered -E "RUN=\|EXIT_CODE=\|Traceback\|out of memory\|BrokenProcessPool"` | `FEASIBILITY=PASS unique=90 executed=90`、`COLLISION_RUNTIME unique=60 missing_checks=0`、`INJECTION_BINDING mismatches=0`、`RUN=PASS` |
| G11 | `python scripts/injection-before-2d/window_timeline.py extract --rollout-run-id 20260911-contract-v2-05,20260911-contract-v3-06`；`… tables --write`；`python scripts/injection-before-2d/plot_sampling_windows.py`；`python scripts/injection-before-2d/plot_injection_before_2d.py --run-id 20260911-contract-v3-06`；`python scripts/injection-before-2d/event_tables.py --write`；`python scripts/injection-before-2d/check_doc_links.py` | `WINDOWS_EXTRACT=PASS groups=14 swap_fail=0`、`WINDOW_TABLES=PASS groups=14 drift=0`、`WINDOWS_PLOT=PASS files=15`、`BEFORE_2D=PASS groups=14 files=98`、`EVENT_TABLES=PASS groups=14 drift=0`、`DOC_LINKS=PASS missing=0`、`XHARD_TIMELINE=PASS route_t=[800,1000] unmask_bands=[4,5] repick_bands=[4,5]` |

## 三、runbook（按阶段与 commit）

0. 写 `XHARD_DIFFICULTY_PLAN.md`；G0。
1. 脚本侧前置（散列作用域、操作元路径、`XHARD_GROUPS`／`GROUPS_V3`、组列表真源、`_static_problems` 循环校验、提取器可选四键）+ 测试 → G1、G6、G8 → commit `10.57 取值域散列按难度作用域并把注入组列表改为契约驱动`。
2. 逐条提交 S1～S8 报批；获批后落地 → G3 → G4 → G6 → G5（tmux）→ commit `10.58 三任务加 xhard 难度字典并把 swap 调度改成通式`。
3. `build-v3`、发起者循环、`--groups`、`specs-diff`、`plots.py`、测试 → G6、G7 前半 → commit `10.59 契约 v3：三任务各加 xhard 组，实跑支持按组过滤`。
4. `plan`／`check` 06、`specs-diff`、`check` 05 复验（tmux）→ commit `10.60 冻结 20260911-contract-v3-06：14 组 1400 条，旧 11 组与 05 逐条相同`。
5. G9 → G10（tmux，日志 `artifacts/injection/20260911-contract-v3-06/logs/feasibility-P01x20.log`）→ `summarize`／`report` → commit `10.61 实跑 3 个 xhard 组 90 条`。
6. 可视化改动 → G11 → commit `10.62 数轴与跑前分布扩到 14 组并合并两次实跑`。
7. 文档 → commit `10.63 xhard 扩展文档与账本`；`git status -sb` 首行无 `ahead`。

## 四、风险登记

| 风险 | 触发 | 处置 |
|---|---|---|
| VideoRepick xhard 冻结候选耗尽 | `plan` 抛 `SpecGenerationError` | 离线证据已基本排除；若发生，不放宽 `MAX_CANDIDATES`，报 `plan_stats` 拒绝分布交用户 |
| VideoRepick worker 卡死（05 已见 seed 相同的 ep26） | 单条 >18 分钟、h5 96 字节 | 手工 `kill -9`，记 `BrokenProcessPool` |
| RouteStick L=10 整局成功率 p^L（p 未标定） | 失败率抬高 | 冒烟先挑 L=10；日志按 L 分桶记录；不改规格 |
| Unmask n=5 demo 静止 314 帧、T≈510～700 | 无 | `fail_safe_limit=2000` 远未触及；`VIDEO_DECODE` 按帧数核对 |
| 快照与 src 版本脱节 | 旧 JSON 配新源码报「缺少字段 ['xhard']」 | CHANGELOG 明记；05 复检不经 `load_sampling_config` |
| `GROUPS` 副本漂移 | 漏改一份静默少画／少查 | before-2d 三份单点导入 + 测试断言 |
| `_check_reproducible` 漏对拍 | 14 组只查 11 组 | 改遍历 `documents`，判定行 `compared=1400` 为证 |
| `env_metadata` 无 xhard | 评测链构造不了 xhard | 明记不做 |

## 五、盲区诚实清单

- 没有跑过 xhard 的任何仿真；被拒率只在 05 布局上离线证明；Repick 关节静止反解在 xhard 上是否仍落在 `B1_MINUS_S_RANGE`，实跑后知道。
- 通式与旧分支的等价只在单测与 4 条 HDF5 对拍上证明，未做 15 格全矩阵重跑。
- RouteStick 单段成功率 p 未从 05 结果反解。
- `plot_injection_before_2d` 在 K=5 时面板尺寸未试过；旧 11 组图是否逐像素不变未验证（不入库，只要表零漂移即可）。
- `campaign check --run-id 06`、`plan` 14 组的耗时未测（估 8～12 分钟）。
- `contract_build.BUILDERS[*](sampling, "xhard")` 未实际调用过，阶段 3 的 `build-v3` 是第一个真实闸门。

## 六、留档与 commit 纪律

- 每笔 commit body 按 AGENTS.md 规则 7 六项写（用户原话、计划、分节实施、意外、实验数字、状态与下一步）。
- 实测数字追加到 `XHARD_DIFFICULTY_PLAN.md` 第一部分之后的「实测结果」子节与 `AGENTS.md` 日志，不改写原计划正文。
- 临时产物放 `artifacts/xhard-smoke/`（不入库）；scratchpad 只放一次性清单。
