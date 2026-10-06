# 清理「MME」自造名 + 第三阶段三模型评估

> 状态（2026-10-06）：计划已获批、用户已下开工令；执行到派出改名子代理 R1 时用户叫停（「先暂停把你的计画写入根目录」「不要再执行了」），R1 已停止、无提交，主检出仍为 `3d0b8778`，GL 未起任何任务。恢复执行需用户再次下令。

## 第一部分：决策信息

### 一、命名（用户 2026-10-06 裁决：照官方；改活代码 + 现行文档）
| 模型 | 展示名（官方 `docs/manual_evaluation.md`） | 代码／参数／路径 ID（官方 `MODEL_TYPE`／权重名） | Python 标识符 | 仓库旧名 |
|---|---|---|---|---|
| 本次评估模型 | FrameSamp+Modulation | `perceptual-framesamp-modul` | `framesamp_modul` | `mme`、`mmevla` |
| GroundSG 两变体 | GroundSG+Oracle、GroundSG+QwenVL | `groundsg`（变体 `oracle`／`qwenvl`） | `groundsg` | `mmesg` |

保留不改（官方名）：家族名 MME-VLA（Symbolic／Perceptual／Recurrent MME-VLA）、`third_party/mme-vla`、`.gitmodules`、上游类 `MMEVLAWebsocketClientPolicy`、上游配置 `mme_vla_suite`。

### 二、改名范围
- **改**：活代码与测试 91 个文件、约 900 处。
  - 文件名：`mme_client.py`、`mmesg_client.py`、`orig_observer/{mme_client_wrap,mme_proxy}.py`、`run_orig_mme.sh`、`orig-mme-client-env/`、`test_mme_transport.py`。
  - 参数：`--mme-variant`（实为 GroundSG 变体）、`--mme-ckpt`、`--mmesg-ckpt`、`--episode-wall-mme`。
  - 环境变量：`MME_PY`、`MME_CKPT`、`MMESG_CKPT`、`MME_VARIANT` 等。
  - 策略标签 `mme`、`mmesg`，以及测试名、契约条目。
- **现行文档也改**：`AGENTS.md`、`CLAUDE.md` 的项目段（标记块不动）、`readme.md`、`scripts/README.md`、`tests/README.md`。
- **不改**：`docs/validation/`、`docs/plans/` 历史留档（约 3200 处；里面有 NFS 真实路径和 SHA256SUMS）。指向磁盘或 NFS 真实目录的字符串（如 `sg-eval/ckpt/mme/...`、`mmevla-testhard*`）也保留原样，旁注「历史目录名」。新增 `docs/validation/legacy-names.md` 写旧名到新名的对照。
- **兼容**：读历史逐局行、预算账本、v7.5eval 留档的工具（`env_client.py`、`client_replay_eq.py`、`orig_results_adapter.py`、`observer_status.py`、`cap_probe.py`、`site_catalog.py`、报告类）读入时把旧标签映射到新名，写出只写新名，CLI 只接受新名。别名表只在 `official_defs.py` 放一份。
- **行为零变化**：只改名字，不改任何逻辑和数值。

### 三、评估（改名合入后）
- FrameSamp+Modulation、SimpleMemVLA、PonderPounce 三个模型；MemER 不跑。
- 只跑第三档（V9 `test-hard`，1600 步，`--strict-cap`），只用 GL A40。
- 43 格 × 每格 2 局 = 每模型 86 局，三模型共 258 局。
- 执行副本用改名合入后的冻结提交新建（`robomme_benchmark-sgeval3`）。

### 四、总耗时（依据第二阶段 sg-eval-gl-20261006-02 的 GL 实测）
第三档单局耗时 = 第二档实测 × 1.5（GroundSG+Oracle 实测第三档 0.72 ÷ 第二档 0.48 = 1.5；GroundSG+QwenVL 为 1.25）：

| 模型 | 第二档实测（分钟/局） | 第三档估计 | 86 局席位分钟 |
|---|---|---|---|
| FrameSamp+Modulation | 0.63 | 0.95 | 82 |
| PonderPounce | 1.13 | 1.7 | 146 |
| SimpleMemVLA | 1.39 | 2.1 | 181 |

| 阶段 | 墙钟 |
|---|---|
| 改名：1 个写入型子代理 + 合并前审查 + 合并 + 合并后核心短测与闸门 | 约 2–2.5 小时 |
| 起跑前：新建执行副本、`RUN_INPUTS`、`CLIENT_REPLAY_EQ`（新名 vs 旧名基线）、三模型本机 smoke 各 1 局 | 约 0.7 小时 |
| GL 跑：6 片（每模型 2 片 × 43 局），4 个现有占位 job 队列（63188714／15／16／19，2026-10-06 时各剩约 34 小时） | 约 1.7–2 小时 |
| 收尾：覆盖与视频核对、成绩表、result.md、commit、按清单 scancel | 约 0.5–1 小时 |
| **合计** | **约 5–6 小时** |

预算：258 条轨迹，第二阶段账本剩余 4302，够用。无 Astra，无付费接口。

## 第二部分：执行细节

### 子代理分配表（计划执行模式；派发前核 `worktree.baseRef=head`、主检出 clean（`third_party/SimpleMemVLA` 子模块内他人改动不动）、记 `BASE`；2026-10-06 核对时 BASE = `3d0b8778`）
| 编号 | 类型 | 可写集合 | 禁触 | 验收 |
|---|---|---|---|---|
| R1 | 写入型 opus，worktree | `scripts/**`（不新增 `scripts/*.py` 顶层入口）、`src/robomme_hard/**`、`tests/**`；子项目 `orig-*-client-env` 的 `uv.lock` 只许 `uv lock --offline` 改项目名 | `src/robomme/**`（受保护）、`third_party/**`、`docs/**`、`AGENTS.md`、`CLAUDE.md`、`readme.md`、顶层 `pyproject.toml`／`uv.lock`、录像器 | worktree 内 `pytest -m 'not slow'` 全过、`pytest -m slow tests/pipeline/eval tests/pipeline/evalx` 全过（超 5 分钟留给合并后）；`git grep -P '(?<![A-Za-z])(mme\|MME\|mmesg\|MMESG\|mmevla\|MMEVLA)(?![A-Za-z])' -- scripts src/robomme_hard tests` 只剩别名表、兼容测试、标注的历史目录名、上游符号 |
| 主会话自做 | — | `AGENTS.md`／`CLAUDE.md` 项目段、`readme.md`、`docs/validation/legacy-names.md`、清单与 GL 操作 | 标记块 | `sync_rules.py check` 不报标记块漂移 |

R1 要点：用 `git mv` 改文件名（保留历史）；`TEST_INVENTORY`、契约 json 同步登记；`client_replay_eq.py` 的基线提交是旧名，要能把旧名路线对到新名路线；commit 前缀 `sub/R1: `。

### 步骤
1. 派 R1 → 合并前审查（sonnet 只读，钉 sha）→ `git merge --no-ff` → 合并后审查：核心短测 `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q`、`ls -1 scripts/*.py` 四入口、录像器零 diff、`UPSTREAM_GUARD=PASS`、`TEST_INVENTORY=PASS` → push → 清理 worktree。
2. 主会话改现行文档与对照表，commit、push。
3. 起跑前三件事：`RUN_INPUTS`；`client_replay_eq.py --base 80a402cc --candidate <新冻结 sha>` 三条路线 PASS；本机 smoke 三模型各 1 局 V9（tmux 前缀 `p3-smoke-`）。然后建 NFS 执行副本，`SMVLA_PY`／`PP_PY`／FrameSamp+Modulation 服务 venv 照第二阶段指向。
4. 清单：照 `docs/validation/sg-eval-gl-20261006-02/records/scripts/gl-scripts_build_manifests.py.txt`，从 `hard_specs.py::_v9_cells` 每格取前 2 局（按局号升序），核对每模型 86 局、43 格各 2 局。
5. GL：新 stage `R3=$N/sgeval-<日期>-03`；6 个任务入队（SimpleMemVLA → PonderPounce → FrameSamp+Modulation），4 个占位 job 各起一个 `seat_worker.sh`（gl-login3 tmux，前缀 `p3-`），预算账本 `$R3/budget-ledger.jsonl`；每片日志一个 Monitor，过滤 `TASK_END`、`EXIT_CODE=`、`NO RECORD`、`reset 拒绝`、`svulkan2`、`EXCLUSIVE`、`RRT`、`Traceback`。
6. 收尾：每模型 `EVAL_COVERAGE=PASS unique_terminal=86`、`EVAL_VIDEOS`、`OFFICIAL_MEDIA=PASS total=86`；成绩表（逐格 + 总成功率，注明每格 n=2）；留档 `docs/validation/sg-eval-gl-<日期>-03/`；commit、push；按清单 `scancel`。
7. 记忆：已完成（新增「模型一律用官方名」，旧条目里指单个模型的 MME 已改）。

### 验收
- 改名：上面的 grep 判定为零残留（别名表等除外），全部闸门 PASS，`CLIENT_REPLAY_EQ` 三路线 PASS（行为未变）。
- 评估：三模型各 86 终态、86 视频、`OFFICIAL_MEDIA fail=0`、`BUDGET_ENFORCEMENT=PASS`。
