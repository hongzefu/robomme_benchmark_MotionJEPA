# V4 步 4～6：抽签／冻结、实跑编排、推理侧（链路层）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`）。录像器未改。本步只动链路层（`scripts/`）与推理侧构建器，
> 不碰任何环境文件（环境 xhard 由并行子任务实现，另见各 `step3b-*` 报告）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `scripts/parity/v4_specs.py`（新增） | `draw`（只 reset 导出规格 → `drafts.jsonl`，来源封存进 header）、`freeze`（核验来源逐项一致 → 按 index 0/3/6 标 `selected` → `specs.jsonl`，禁覆盖）、`load_specs()`（唯一读取入口） | 3.2～3.4；Codex 审计 #6（身份散列剔除 `selected` 等管理字段，不复用甲的 `identity_sha256`）、#7（来源在抽签时封存、冻结时逐项核验） | `test_v4_specs.py` 7 条；冒烟见下 |
| `v4_specs.py::SEED_RULE` | V4 专用 seed 段 `4_000_000 + env_code×100_000 + episode×100 + attempt` | 计划只给了公式形式、没给 offset；取与 train/test/val/heldout 四代都不重叠的段（测试穷举验证不相交） | `test_seed_rule_disjoint_from_existing_layouts` |
| `v4_specs.py::RECOVERY_RULE` / `env_kwargs` | 抽签按 episode 号开 fail recover（≤2 z、≤5 xy，与官方 `EpisodeJob.recovery_mode` 同规则） | **计划外发现**：recover 会改变 reset 期抽样（`inject_fail_grasp`），抽签若不开 recover、实跑按官方规则开，回注必然对不上 | `test_recovery_rule_matches_official_episode_job` |
| `scripts/parity/train_split_runner.py`（`--identity-source`） | `train_metadata`（默认，逐字不变）/ `formula`（按 V4 seed 公式硬校验） | 3.5：xhard 身份不在官方 metadata 里，原逻辑必然 `SystemExit` | 冒烟实跑经 formula 分支 4/4 通过；原值分支代码未动 |
| `scripts/parity/v4_rollout.py`（新增） | `run`：先跑 selected，失败按 H4 在本环境候选内按 `1,2,4,5,7,8,9` 逐条递补，不追加抽签；`--identities-from` 严格重放上一轮全部身份；`compare`：V2a 终态一致＋V2b 成功局 HDF5 逐位（前置有效非空检查＋根属性比较，不改 V3 的 `compare_h5_pair`） | 3.3③、H4、第五节 V2 拆层 | 冒烟两遍＋对拍 PASS |
| `src/robomme/env_record_wrapper/episode_config_resolver.py::BenchmarkEnvBuilder.from_v4_specs` / `_v4_kwargs` / `v4_episodes` | 并列的快照构建路径：seed/difficulty/sampling_config/规格/recover 分档全取自快照，runtime 四项不等即拒；`resolve_episode` / `get_episode_num` / `make_env_for_episode` 仅在 `_v4` 非空时走新分支 | 第四节 4.2；src 不反向依赖 scripts（调用方先 `load_specs` 再传入） | `test_v4_env_builder.py` 3 条（含原 metadata 路径 `_v4 is None`） |
| `scripts/eval/v4_eval.py`（新增，E1） | 逐局跑策略写 `eval_results.jsonl` / `eval_summary.json`，`--join-results` 打印 V5e 判定行 | 第四节 | 冒烟见下 |
| `scripts/parity/v4_combos.py`（新增） | V6 组合覆盖：冻结组合清单逐组合收窄 xhard 范围、reset 级＋演示级两级都报 | 口径 14 / 步 3c | 待各环境落地、组合清单冻结后实跑 |

## 二、冒烟实测（本机 sm_89，只作调试）

```bash
uv run --no-sync python -m scripts.parity.v4_specs draw --run-id smoke-01 --tasks PatternLock,RouteStick \
  --candidates-per-env 4 --max-reset-attempts 6 --out artifacts/newtask-v4/smoke-01/draft/drafts.jsonl
# DRAW_TASK PatternLock ok=4 attempted=4 / RouteStick ok=4 attempted=4
uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts .../drafts.jsonl --out .../specs.jsonl --candidates-per-env 4
# FREEZE_DONE rows=8 selected=4 envs=2 candidate_shortfall=0
v4_rollout run --label run1 → ROLLOUT_DONE rollout_attempted=4 rollout_ok=4 backfilled=0 selected_shortfall=0（411 s）
v4_rollout run --label run2 --identities-from run1 → rollout_ok=4（529 s）
v4_rollout compare run1 run2
# NEWVALUE_REPLAY=PASS identities=4 terminal_mismatch=0 compared_success=4 sha_equal=4 field_mismatch=0 empty_or_invalid=0
```

每局 `spec_binding = {mismatch 0, unattributed_mismatch 0, unused 0}`。

**规格真被消费（V3g 的离线雏形）**：把冻结规格里 PatternLock 的 `actions.path_nodes`、RouteStick 的 `actions.nodes`
倒序后回注，任务序列随之改变（例如 PatternLock/0 的第 3 步由 `move forward-left` 变为 `move forward`）；原样回注零不等、零未消费。

**推理链路**：`v4_eval` 对同一快照 RouteStick/0 跑 dummy 策略，`status=timeout steps=1301`（dummy 预期结果），
`spec_binding` 零不等零未消费。全部 4 局：`EVAL_PIPELINE=PASS episodes=4 runtime_ok=4 join_missing=0`（4 局均 timeout，dummy 预期）。

## 三、计划外与设计取舍

1. **recover 分档必须在抽签时就开**（见表）。这也意味着推理侧用快照起环境时要带同样的 recover 分档，
   否则规格回注对不上；代价是 episode 0～5 的演示视频里带「失败再恢复」片段——**待用户确认**这一口径。
2. **mismatch 归因的意义有限**：V4 的实跑与推理都用快照内嵌的同一份配置与 seed，回注的正确结果就是 `mismatch=0`；
   `decision_key` 归因只在「故意用不同配置回注」时才有信息量。V3g 建议直接以 `mismatch=0, unused=0` 为判据，
   外加改坏规格必出差异（`SPEC_NEGATIVE`）。
3. **H4 递补后 `selected` 的落盘**：本步把递补结果只写进 `results.jsonl`（`role=backfill`），**没有改写冻结的 `specs.jsonl`**；
   推理侧要评递补后的集合，需要一份「按 results 重标 selected」的新快照（身份散列不变）。这一步留到步 7 全量时按需实现。
4. seed 段 offset 的取值是实施方选的（计划未给），如需改动只影响尚未冻结的快照。
