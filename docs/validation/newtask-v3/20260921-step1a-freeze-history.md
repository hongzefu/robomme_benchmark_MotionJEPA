# 步 1a 留档：冻结历史证据（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 1a。只读官方 Git 对象与本地目录，未启动仿真、未改动 `src/robomme/`。

## 一、做了什么

新增 `scripts/train_split_parity.py freeze-history` 子命令：

```bash
uv run --no-sync python scripts/train_split_parity.py freeze-history --output artifacts/train-parity/v3-native
```

```text
HISTORY_FREEZE=PASS rows=1600 subset=144 identity_mismatch=0 missing=0
HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0
HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing
# 历史成品探测点缺失：data/robomme_data_h5, artifacts/native-baseline, /data/hongzefu/robomme_benchmark-restore-DataGen
# 全集动作比较原始结果：different_element_count=217242 max_abs_diff=0.007857919612339614 passed=False（阈值 1e-08）
# 全集 10 条帧数不符中落入 144 条子集的：2 条：BinFill/episode_11；PickHighlight/episode_3
```

冻结产物（git 跟踪）：

| 文件 | 内容 | SHA-256（前 16 位） | 字节 |
|---|---|---|---|
| `scripts/configs/newtask-v3/history/generation_report.json` | 官方历史报告原文 | `c0d1fddd39d5f7bf` | 1544554 |
| `scripts/configs/newtask-v3/history/generation_report.md` | 官方历史报告原文 | `c753ed36af613e03` | 13461 |
| `scripts/configs/newtask-v3/history/history_projection.json` | 144 条 R1a 投影与缺证登记 | 见运行留档 | — |

## 二、R1a 可投影字段与投影结果

投影字段固定为 `identity / recovery_mode / success / timestep_count`，**不含历史动作数值**。

- 历史报告 `generation.results`（1600 条）逐条带 `task/episode/seed/difficulty/recovery_mode/attempt_count/ok/timestep_count`；`validation.generated.audits[*].episodes` 与 `validation.official.audits[*].episodes` 另有逐 episode 的 `timestep_count/final_is_completed/joint_shape/joint_dtype`。
- 历史身份与本轮步 0 冻结的官方身份逐条核对：`identity_mismatch=0`，1600 条无缺漏（含 170 条非公式 seed，报告侧同样是实际 seed）。
- 144 条子集投影 `missing=0`，每条都有生成帧数、参考帧数与成功标志，`ok=true`、`final_is_completed=true`。

## 三、明确缺证的三项

1. **历史动作逐局数值（R1c）**：报告只有 `validation.joint_action_comparison` 的**全集**统计——761885 个向量、6095080 个元素、`different_element_count=217242`、`max_abs_diff=0.007857919612339614`（阈值 `1e-8`）、`passed=false`，没有逐局摘要。217242 不能拆到子集，唯一最大差位置 `BinFill/episode_99/timestep 625/element 5` 也不在 144 条子集内。故记 `HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0`，按用户决策不阻塞本轮完成。
2. **历史 HDF5 成品（R2）**：三处探测点 `data/robomme_data_h5`、`artifacts/native-baseline`、`/data/hongzefu/robomme_benchmark-restore-DataGen` 本次实测全部不存在，记 `HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing`。官方发布集 revision 为 `a5e4e25ffe8af34f64944f9533d06455ce5f8337`，恢复到 `data/robomme_data_h5/` 之后才能跑步 5e 的 R1b。
3. **报告标称 HEAD 不是完整运行源码**：报告 `current_head=9430e20bfcf59116d525778b60663520b22f63e6`、生成时间 `2026-07-15T04:14:21Z`、`status=failed`、`uv_lock_sha256=983de83f…`。按方案风险登记，该提交的校验器还限制 9 条，至 d53 才改 100 条，故仍以 d53 为可重跑源码，报告只冻结原文。

`different_element_count` 在投影文件里显式写明定义为 `delta != 0.0` 的元素数，**不是**「超过 `1e-8` 的元素数」，避免后续混称。

## 四、子集内已知的两条帧数不符

全集 10 条 `timestep sets do not match` 中，落入 144 条子集的恰好 2 条，与方案第二部分 9.5 的表一致：

| 环境／episode | 历史生成帧数 | 发布参考帧数 |
|---|---|---|
| BinFill／11 | 576 | 584 |
| PickHighlight／3 | 648 | 652 |

这两条是**历史生成对官方发布集**的差异，不是本轮五路之间的差异；步 5e 的 R1b 会重跑并记录本次结果，不得用它们解释新接口的注入差异。

## 五、测试

```bash
uv run --no-sync python -m pytest tests/lightweight/test_train_split_parity.py -q
```

12 项全过（0.05 s），新增 4 项覆盖步 1a：投影只含 144 条与可比字段、全集动作比较必须保持 `failed` 与原始数值、子集内恰好两条帧数不符且最大差位置在子集外、三处历史成品探测点均为缺失。

## 六、本步之后的状态

- G1 已过（步 0），历史证据冻结完成；R1c／R2 明确 `NOT_RUN`，R1a 的历史一侧已就绪，等步 1b／5e 用新跑的 A 路结果与之比对。
- 下一步：步 1b——实现 `run`／`compare`，新增 `scripts/train_split_comparison.py` 的范围适配器并先过 G5 离线夹具，再上 greatlakes 跑 `BinFill/easy/episode_0` 的 A1／A2 冒烟与 3 job 版 P0。
