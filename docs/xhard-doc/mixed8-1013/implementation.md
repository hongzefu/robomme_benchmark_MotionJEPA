# 八档循环实施记录

最新本机阶段结果见 [result.md](result.md)：W5 已按用户批准的三项豁免合入，核心 679 通过、精确 4 个旧失败；真实生成 127/128，正式校验期望 100、实有 99，四项整体因唯一缺失身份失败。下面各阶段说明保留其原提交时点，不能把较早“尚未运行”状态读成最新状态。

截至代码阶段提交 `1860bd8186be5c3d36a13555b6f2d24b5f8d65b4`，W1、W2、W3、W4、W6 已审查、合并并推送。W4 两轮审查后的最小修复已获用户批准并通过增量重审；W5 与两次本机冒烟尚未执行。本记录不是生成结果，不能据此宣称 100 个实际样本校验通过。

## 用户指令与版本

用户原话：「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1013-mixed8-400ep-plan.html 开始实现 有问题问用户」。

获批计划为仓库根目录 [1013-mixed8-400ep-plan.html](../../../1013-mixed8-400ep-plan.html)，开工锚点为 `94c6a90b312c35ebf1a47940cd4d8159523212ce`，初始工作区干净。开工前独立全文审查：`PLAN_CONSISTENCY_REVIEW=PASS base=94c6a90b312c35ebf1a47940cd4d8159523212ce findings=3 blocking=0`。三处文字统一已提交 `aa6d4d590e9f31355174f40307e41b064ecb94c8`，未改变失败处理或判据。

本机为 `sled-vail` 环境 B，仓库与共享盘存在，两张 RTX 6000 Ada；SSH 别名符合判据表，`micromamba`、`uv` 可用。`.venv` 为 CPython 3.11.14，editable 指向本仓库 `src/`，ManiSkill 锁定版本未改。Codex 配置的子代理数为 32，当前宿主实际槽位为 16 个子代理，未声称实测 32 个并发。

## 已合入与验证

| 子任务 | 合并提交 | 内容 | 独立审查 |
|---|---|---|---|
| W1 | `1aad348dd6f5c60451501be96e1d339903a20fd3` | 显式循环解析、缺档过滤，既有 seed 公式不改 | `PRE_MERGE_REVIEW=PASS task=W1 findings=0` |
| W2 | `732658ae9d4ce082ee728a49886a631257ad41c4` | 循环生成、11 任务绝对 FailRecover 分配、公式重试、证据、崩溃产物隔离与停档 | 第二轮 `PRE_MERGE_REVIEW=PASS task=W2 round=2 findings=0` |
| W3 | `4d505df85908688068742a08158b38e112b4c1b1` | H5 四项校验、独立身份对账、原版 golden、边界规则骨架 | 第二轮 `PRE_MERGE_REVIEW=PASS task=W3 round=2 findings=0` |
| W4 | `f43d455dad054a4b4956a453f3b2eca1c13b5d99` | 最重档内存探针、多卡阶梯、完整停止清理与证据 | 获批增量重审 `PRE_MERGE_REVIEW=PASS task=W4 round=3 user_authorized=1 findings=0` |
| W6 | `1860bd8186be5c3d36a13555b6f2d24b5f8d65b4` | 目录文档与已合代码一致，历史实测正文未改 | `PRE_MERGE_REVIEW=PASS task=W6 findings=0` |

每个写入代理使用独立工作树、独立虚拟环境与专属分支，主会话保留其 `sub/` 提交并以 `--no-ff` 整合。所有代理均显式使用 `gpt-6.1-sol`、`high`；只读探索使用 `gpt-6-luna`、`high`。所有子代理未自行推送；主会话合并后检查并推送。

合并后核心短测命令：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest tests/lightweight/ src/robomme_xhard/tests/ -m 'not gpu and not slow' -q -rf
```

W1 合并后 493 通过，8.32 秒；W2 合并后 523 通过，8.74 秒；W3 合并后 573 通过，12.57 秒。三次均退出 1，失败身份集合恰为计划 R-0b 的四项，另有 2 项跳过、137 项排除：

```text
tests/lightweight/test_TaskGoal.py::test_swingxtimes_multiple
tests/lightweight/test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal
tests/lightweight/test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except
tests/lightweight/test_step_error_handling.py::test_step_error_returns_status_error
LIGHT_TESTS=PASS failed=4 new_failures=0 passed=573
POST_MERGE_REVIEW=PASS merge=4d505df85908688068742a08158b38e112b4c1b1 files=19 tests=573passed_4known_failed
```

W3 合并后定向命令 `UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m pytest src/robomme_xhard/tests/test_check_mixed_h5.py -q`，50 通过、6.22 秒、退出 0；W2 常量依赖断言实际通过，无依赖跳过。原版 16 份 golden 的元数据导出耗时 13.72 秒，来源 revision 为 `a5e4e25ffe8af34f64944f9533d06455ce5f8337`，每任务只读 `episode_0`。主会话独立抽查 BinFill、PatternLock 的全部 timestep 元数据：`GOLDEN_SPOTCHECK=PASS task=BinFill source_episode=0 excluded=8`、`GOLDEN_SPOTCHECK=PASS task=PatternLock source_episode=0 excluded=6`。

冻结目录检查命令（退出 0，另查目录工作区状态为空）：

```bash
git diff --quiet 94c6a90b312c35ebf1a47940cd4d8159523212ce 4d505df85908688068742a08158b38e112b4c1b1 -- src/robomme/ src/robomme_xhard/base.py src/robomme_xhard/configs.py src/robomme_xhard/envs/
```

`PROTECTED=PASS base=94c6a90b312c35ebf1a47940cd4d8159523212ce tip=4d505df85908688068742a08158b38e112b4c1b1`。`git diff --check` 退出 0。代码验证与反例日志保存在本机 `artifacts/mixed8/dev-logs/{w1,w2,w3,w4}/`，不含真实生成数据。

## 实施中调整与审查修复

唯一机制补齐：标准库 `shutdown(cancel_futures=True)` 无法终止已运行 worker。经只读对抗审查 `ADJUST_REVIEW=PASS scale=same findings=0`，仅在循环模式开启 `--stop-on-pool-crash` 的首次损坏支路，保存各池 worker 快照、终止并等待退出，再关闭池、隔离与写摘要退出 3。无新开关、守卫、重试或回退，已写入计划的「实施中调整」。

W2 首轮审查发现默认重建的隔离竞态，修复为先等待损坏池的管理线程终止 worker，再隔离当前与连带产物。两个 CPU 反例在旧版本复现、修复版通过；第二轮审查通过。

W3 首轮审查发现不可读 H5 的结构假通过、伪装 base 难度导致语义预期空集假通过。修复保持独立预期集合，完整循环冻结 100 个样本、52 个 xhard 身份与 80 个数量项；不能读取或执行的项明确失败。旧版本两反例均复现，修复版通过；第二轮审查通过。其余 10 任务的规则仍待 W5，当前 `EXEMPT` 为空。

## W4 两轮审查与后续裁决

暂停时 W4 两条子提交尚未合入主分支：初版 `60f4e073b155bc98022f476baaa3e9fa69d1ba2f`，第一轮修复版 `9385c5a92fa6bf88034d08517ee5177fb58b148d`，分支 `codex/mixed8-w4`。独立工作树与日志保留，当时没有自行开展第三轮修复。

第一轮审查发现外层终止信号留下独立生成器组、已中止档坏 JSONL 尾行使汇总证据丢失；修复版真实 CPU 测试验证本组清零、旁组存活，且坏行保留原字节、解析失败与清理证据。定向 35 通过、2.30 秒；其工作树核心 528 通过、精确 4 个旧失败、10.92 秒。

第二轮结果为 `PRE_MERGE_REVIEW=FAIL task=W4 round=2 base=60f4e073b155bc98022f476baaa3e9fa69d1ba2f tip=9385c5a92fa6bf88034d08517ee5177fb58b148d findings=1`。确定性窗口：`run_cell` 构造成功 `summary` 后仍写资源文件及清理产物，此时处理器收到 `SIGTERM`／`SIGHUP` 只改变局部 `aborted_by`，已构造的结果可能仍为成功，随后阶梯继续。

已向用户呈现最小修复范围：仅测速脚本 `run_cell` 的信号收尾与最终结果落盘，加对应测试的尾部信号反例；最终中止状态必须传到档位结果并停止后续阶梯，不加开关、守卫、重试或回退，再做一次增量独立审查。计划 G1 明确「两轮仍 FAIL 交用户」，本轮不自行开展第三轮修复。AWS 监控开销、测速与全量仍未执行。

随后用户原话：「允许最小修复并增量重审（推荐）」。获批修复提交为 `554cc67f105d464f2b9ee0abb1f00d6cbdcff3c5`：生产代码仅 6 行新增、4 行删除，把最终摘要写入、汇报与返回移到恢复原信号处理器之后，使用最终中止状态确定结果。资源写入／产物清理 × SIGTERM／SIGHUP 四个反例在旧提交上复现四项失败，在修复版均确认只运行一档、下一档未启动、最终失败。定向 39 通过、2.71 秒；子工作树核心 532 通过、精确 4 个旧失败、11.26 秒。

`PRE_MERGE_REVIEW=PASS task=W4 round=3 user_authorized=1 base=9385c5a92fa6bf88034d08517ee5177fb58b148d tip=554cc67f105d464f2b9ee0abb1f00d6cbdcff3c5 findings=0`。主会话保留三条子提交合入后，核心 612 通过、精确 4 个旧失败、2 跳过、137 排除、15.12 秒、退出 1：`LIGHT_TESTS=PASS failed=4 new_failures=0 passed=612`、`POST_MERGE_REVIEW=PASS merge=f43d455dad054a4b4956a453f3b2eca1c13b5d99 files=2 tests=612passed_4known_failed`。冻结目录零差异，验证后已推送。

W6 仅改生成器目录 `CLAUDE.md`，三个 CLI 帮助退出 0、五处新增链接有效、历史第五至十四节逐字节未改：`W6_DOC=PASS files=1 links=5 cli_help=3 history_bytes=unchanged diff_check=0`。独立审查与主会话合后文档检查通过，未运行无关测试。

## 后续边界

代码阶段已完成，后续为本机 smoke 一 1 条与 smoke 二 128 条，之后 W5 填规则、具名豁免由用户批准、第一次实际校验报告。AWS 阶段依旧等用户启动。起跑信息另见 [launch.md](launch.md)；本记录形成时尚无本轮 GPU 工作负载，不能将 CPU 假进程测试当作真实生成或 AWS 测速验收。
