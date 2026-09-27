# V6 计划审计报告（主审部分，四份分报告仍在生成）

分报告（写完后落在本目录）：sec_A_frozen_runbook.md（头部/口径/冻结清单/runbook）、sec_B_numbers.md（1.3/1.4 数字复核）、sec_C_tiers.md（三档数值与键名）、sec_D_sim.md（模拟器实测）。

## 主审已核条目

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注 |
|---|---|---|---|---|
| 五入口 | scripts/ 顶层五入口冻结 | ls scripts/*.py | 一致 | dataset_replay、evaluation、generate_dataset_newseed、run_example、seed_layout 共 5 个 |
| seed 偏移 | xhard 重冻 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6 | 读 v4_specs.SEED_RULE、seed_layout.LAYOUTS | 与数据集 seed 不撞，但有结构问题 | 公式 offset+env_code×1e5+ep×100+attempt，每段跨度约 1.6e6，间隔 2e6 不重叠；V5=4e6，heldout 最大约 3.1e6。但 tests/lightweight/test_v5_xhard_obb_fix.py 离线扫描已用 5e6、6e6 起的 seed（只是测试，不撞数据集） |
| **seed_rule 单一 header** | xhard 档 = 12 环境 v5-01 行回注 + 4 环境 6e6 重冻 | v4_specs.py 的 header 校验 `header["seed_rule"] != SEED_RULE` | **不一致（必须改）** | 同一份 v6-01/xhard/specs.jsonl 里混了 4e6 与 6e6 两种 seed 规则，现有 header 只能封存一条 seed_rule；计划需说明是按环境记 seed_rule 还是把 xhard 回注行与重冻行拆成两份快照 |
| 测试清单遗漏 | 2.0 tests 行 | grep tests | **遗漏（建议改）** | tests/lightweight/test_v4_specs.py::test_seed_rule_disjoint_from_existing_layouts 只校 V4 单段，新增 4 个偏移后要扩展，计划 tests 行未列 |
| spec_kind | 2.0 把 spec_kind_for 改成族判断 | 读 utils/episode_spec.py | 部分一致（建议改） | 现状只有字面 `== "xhard"` 才返回 `native-newvalue/1`，xhard1/2/3 不改会被标成 `native-parity/1`；计划未说要不要升 `native-newvalue/2` 以区分 VUS/BUS/VR/MoveCube 重冻后 v5-01 旧规格（旧规格喂给 V6 代码时现在只会靠 decision 归因报错，不会在 kind 层面拒绝） |
| v4_eval 兼容 | 3.1「推理 v4_eval 默认预算不变」 | 读 scripts/eval/v4_eval.py、episode_config_resolver.from_v4_specs | 一致 | difficulty 从规格行取、不写死档名；`--max-steps` 默认 1300 |
| seed_layout.DIFFICULTY_ORDER | 2.0「不动」 | 读 scripts/seed_layout.py | 一致 | 值为 ("easy","medium","hard")，只服务原三档数据集，不动合理 |
| 磁盘 | 风险 #7 80～100 GB | df -h /data | 余量够 | /data 剩 2.4T（已用 82%） |


## A 段分报告全文见 sec_A_frozen_runbook.md（已完成）
