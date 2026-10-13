# 阶段零结果

本页保留阶段零、W1 接续及当时停工的历史事实。最新状态：W2 已按后续批准的 2.95.6 计划整合为 2.96，主检出核心 427 通过且无新增失败；阶段 D 在 ButtonUnmaskSwap 7700 的建场按钮包络读取失败，已停止，四卡 smoke 与全量未启动。实际版本、日志和只读定位见 [阶段 D 结果](../xhard-1012-swapv2-smoke/result.md)。

阶段零闸门通过。三十个母 seed 中，口径 B 通过二十七个，剔除三个，未超过用户规定的六个停止上限。完整按钮包络与只用按钮底座的 G 在三十个 seed 上均相同。尚未实施 W2，尚未验证真实交换轨迹，不据此宣称生成成功。

## 版本、命令与退出状态

预扫从干净提交 `adefbe3e94b5fb2acfe78ec7ba69cf5611c74207` 启动，命令见 [启动档案](launch.md)，实际会话 `xh-swapv2-scan-1012`，日志 `artifacts/logs/xh-swapv2-scan-1012.log`。仅三十 seed 的 reset，无 rollout，无换 seed 或重试。`EXIT_CODE=0`，完整 JSON 与日志保存在 `records/graph_scan.json`、`records/graph_scan.txt`。

## 实测判定

- `FREEZE=PASS files=426`，冻结日志退出零，旧目录全部只读。
- `OLD_RUN_READONLY=PASS files=426`，逐文件及目录权限核验通过。
- `BUTTON_ENVELOPE=PASS buttons=3 base_box=1 cap_cylinder=1 cap_inside_base=1`。
- `SWAP_V2_GRAPH_SCAN=INFO seeds=30 b_pass=27 b_reject=3 base_envelope_diff=0`。
- `GRAPH_SCAN_GATE=PASS b_reject=3 limit=6`。

| 官网编号 | 任务 | 通过 / 总数 | 剔除 seed | 孤立槽 |
|---|---|---|---|---|
| 2.3 | VideoUnmaskSwap | 10 / 10 | 无 | 无 |
| 2.4 | ButtonUnmaskSwap | 9 / 10 | 10500 | 3 |
| 3.2 | VideoRepick | 8 / 10 | 10000、10400 | 均为 0 |

包络相对底座结果相同仅覆盖本次三十种布局，不代表任意布局中二者等价。三个剔除 seed 不补、不换；真实运行期仍须逐段重证、槽位绑定、端点及子步检查。

## W1 合并前材料

W1 工作树基线 `a00efbe1c00569934f12f4dd398d2a8b0e20e118`，分支 `codex/swapv2-w1`。三个提交为 `ff19c957cde4cda1d79b9806ae25935e491ecfa4`、`7f7748288ba654650516ccd9ec70432c5e436ad7`、`abfa4110a348a9985efb91aa27e351504beeb9eb`。主会话复核 `REVERT_V1=PASS paths=2 diff=0 removed=10`、`SRC_ROBOMME_ZERO_DIFF=PASS base=0ec9951b`，两份引入源码完整 SHA256 与计划一致。代理测试证据 `VENDOR_TESTS=PASS tests=36 exit=0 seconds=3.67`，日志已归档。

独立审查 `PRE_MERGE_REVIEW=PASS`，锚点为上述基线至 W1 最后提交。审查确认撤回范围、十个恢复文件、两份引入文件、来源文档及测试符合计划，受保护目录零差异，子提交父链完整。审查未运行测试。W1 临时没有 `swap_plan.py` 属于计划中间状态，W2 合入前不运行生成。

## 事件与边界

归档 `.log` 被仓库全局忽略，因此原始日志改以 `.txt` 留档，没有改变日志内容或忽略配置。没有机制、接口、失败处理、预算与验收口径调整。下一步按批准计划合并 W1、核心短测，再派 W2。

## W1 合并后停止：核心短测新增失败

W1 已按计划合并为 `df4c30780569c9083c0f98c94f44b6a1493f155e`（2.95，保留三项子提交）。运行命令：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest tests/lightweight/ src/robomme_xhard/tests -m 'not gpu and not slow' -q -rf
```

结果为 `5 failed, 353 passed, 2 skipped, 118 deselected, 2 warnings in 8.09s`、`EXIT_CODE=1`。逐节点比对计划指定的基线日志，四个原有失败完全相同，新增唯一失败为 `src/robomme_xhard/tests/test_contract.py::test_s3_layout_fallback_to_root_jsonl`。实际 `task_success=None`，测试断言为 `0`。`CORE_SHORT=FAIL new_failures=1`，完整日志 `records/w1_core.txt`，节点差异 `records/w1_core_nodes.json`。

只读定位：W1-a 把 `test_contract.py` 恢复到 `0ec9951b`，其中 `_s3_root` 的两条 JSONL 测试记录没有独立 `task_success` 字段；W1-c 把 `tools/layout.py` 恢复到 `3083af74`，`_canonical_result` 遇到缺失成功字段保持 `None`。计划把 `test_contract.py` 恢复到 `3083af74` 放在 W2-b，因而 W1 阶段的工具与测试夹具版本不配套。两个历史版本的测试只差上述两条记录新增 `task_success=1/0`，并没有修改断言。复核命令：

```bash
git diff 0ec9951b 3083af74 -- src/robomme_xhard/tests/test_contract.py
git show 3083af74:src/robomme_xhard/tools/layout.py
```

按计划闸门「停止后续合并、不 push，交用户」已停止实施；W2 未派，GPU 契约、四卡生成及全量均未启动。本轮冻结、预扫 tmux 均已自然退出；没有停止或改动用户其他会话。W1 合并及三个子提交共四项只留本地，上游停在 `9d133d92`（2.94.8），这是合并后验收失败的明确例外。停止证据保存在本工作区，未将失败合并推到远端。

候选处置：修订计划，把原属 W2-b 的 `test_contract.py` 原样恢复提前至 W1 的后续修补，重新独立审查并运行同一核心短测，保持成功字段语义和全部断言不变。此处仅记录候选，不执行；待用户裁决与修订计划完整审查后继续。

## 用户批准修订计划，实施继续停止

用户在停工问题中选择原话：「修订计划，重新交我审查」。本轮仅修订 `1012-swap-pairing-v2-plan.html`，把 `test_contract.py` 的文件归属从 W2-b 移到 W1，最终工具恢复集合由十文件变为十一文件。已执行的 W1 三提交和失败合并保持原样；计划新增 W1-d 单文件恢复、独立审查、整合后原核心短测三步。修订版及本档案提交为 2.95.1，等待完整用户审查和重新开工令；不修改测试夹具、不运行核心短测或 GPU、不推送失败合并。

正文保留两个规定的一级标题，更新第一部分口径、验收与步骤，第二部分逐文件集合、代理唯一归属、闸门、接续命令、风险与提交纪律。原图保留，仅明确图一为首次实施的历史示意，本次接续按 A′ 表与命令。文档验证仅检查链接、结构、目录点击、页面报错及截图，不执行仓库测试或生成命令。

文档检查：`git diff --check` 通过；规定的两个一级标题计数为二；相对链接与锚点存在。用一次性 Playwright 环境验证目录六个跳转、三个图像加载、页面零异常和无水平溢出，`PLAN_DOCUMENT=PASS parts=2 figures=3 toc_clicks=6 page_errors=0`。主会话目视检查三张图及文首、修订裁决截图：箭头落点正常，框与文字无重叠、无截断和缺字，颜色说明一致；没有改图的几何，仅给图一增加历史范围说明。截图位于 `artifacts/plan-review/swapv2-revision-1012-final/`，机器可读摘要存于 `records/plan_document_validation.json`。`IMPLEMENTATION_STOPPED=PASS code_diff=0`，源码、测试与依赖没有本轮修改。

独立固定提交审查 `STATIC_REVISION_REVIEW=PASS`，锚点 `4259009737c295da6338c3d576649f53e27ac443`，确认文件归属、十一文件集合、接续步骤、成功字段语义及重新批准边界一致。随后文档复核补足原提交纪律漏写的 W2-c，并把 K14 的中间态表述明确为原 X5 的禁生成约束，没有改变执行口径。完整提交差异检查发现归档日志六行行尾空白，文档记录仅去掉行尾空白，原日志 `artifacts/logs/xh-swapv2-w1-core-1012.log` 保持原样。修整提交 2.95.2，后续 W1-d 合并编号顺延为 2.95.3；仍待用户审查，不恢复实施。

## 2.95.2 获批后的 W1-d 接续

用户原话：「同意修订后的 2.95.2 计划，开工继续。有重大口径调整一律停工问我，全量仍在 smoke 后单独报批。」批准基线为 `dbe74421087f08ae30310e1aed7c944434ca5399`，工作区干净。环境再次符合 sled-vail 环境 B，SSH 别名和并发配置符合规则；GPU0 使用 1286 MiB / 46068 MiB，利用率零。本阶段仅 CPU。

原 W1 修改代理在其独立工作树快进到批准基线，仅从 `3083af74` 原样恢复 `src/robomme_xhard/tests/test_contract.py`，提交 `09b22e778171f774e77a88d777c1ff72e9d275ba`。定向测试一项通过，2.69 秒，退出零；包路径命中独立工作树。独立审查 `PRE_MERGE_REVIEW=PASS`，主会话复核来源字节与保护目录零差异，再以 `--no-ff` 合并为 `e5879c798deceb29c524840c969cedfd5a734e7c`（2.95.3）。三个原子提交和前次失败合并保持原样。

- `W1_FIXTURE_BYTES=PASS files=1 diff=0`。
- `RESTORE_V1_FINAL=PASS files=11 diff=0`。
- `SRC_ROBOMME_ZERO_DIFF=PASS base=0ec9951b`。
- `W1_FIXTURE_TEST=PASS tests=1 exit=0 seconds=2.69`。
- `CORE_SHORT=PASS new_failures=0 baseline_failures=4 resolved_fixture=1`。

合并后使用前述相同核心命令，实测 `4 failed, 354 passed, 2 skipped, 118 deselected, 2 warnings in 7.69s`，pytest 退出 1；逐节点比较确认四项失败与固定基线完全相同，新失败为零，前次夹具失败已解决。此处不把 pytest 退出 1 写成退出零，也不将有基线失败的整套测试称为全部通过。通过计划的节点差异闸门后立即 push；远端已从 `9d133d92` 快进到 `e5879c79`。定向与核心日志归档为 `records/w1_d_fixture.txt`、`records/w1_d_core.txt`，节点比对为 `records/w1_d_core_nodes.json`；原始日志保持在各自 `artifacts/logs/`。

## W2 派发前停止：静态前提失败处理存在冲突

只读核对锚点 `e5879c798deceb29c524840c969cedfd5a734e7c`。计划第一部分 K7 明确规定：交换对象盒体集合不同形时抛 `SceneGenerationError`；3.1 与第二部分 1.3 的 `same_shapes/same_height` 却规定前提不满足时不报错，记录 `graph_static=false` 并继续逐段重算可行性。反例为任意两个对象的 `half` 不同：K7 要求立即拒绝，另一处要求继续认证，不能同时实现。仅高度不同并不直接违反 K7，但动态分支的设计也需与最终选择一致。

独立审查确认计划没有明确文本优先级；U1–U13、V1–V3 和本次夹具恢复裁决也没有选择这一分支。固定 V9 的 `plan_balanced_swaps(adj, ...)` 接收固定邻接矩阵，没有形状、高度或动态图参数，无法由该函数代用户裁决。

依据本轮用户「有重大口径调整一律停工问我」与规则第 2 条的失败处理变更边界，主会话在派发 W2 之前停止实施，等待用户决定：静态前提不满足时立即拒绝，或保留动态认证并另明确其重算与选对规则。此处只记录候选，不修改权威计划、不自行选取语义。W2 管理工作树已创建于 `/home/hongzefu/.codex/remote-control-host/worktrees/swapv2-w2/robomme_benchmark_newtask-v3-MotionJepa1006`，基线为上述 2.95.3；没有派 W2 代理，没有写入配对代码，也没有 GPU 契约、四卡 smoke 或全量。本轮没有启动 tmux，用户其他会话不动。

## 同形与等高前提实测（裁决前只读核对）

用户原话：「你先核对一下是否都满足这个前提。然后我再判断」。在 HEAD `061058b4969d35e14245776343902c5652ce6d10`（工作区干净）用只读探针 [`records/swap_premise_probe.py`](records/swap_premise_probe.py) 对阶段零的同一批 30 个母 seed（输入 `records/graph_scan.json`）逐个 reset。当前 HEAD 处于 W1 中间态、子类没有规划器钩子，探针在进程内包装三个 xhard 子类的 `_load_scene`，在其末尾（与 v1 `certify_swap_plan` 调用时点相同）读交换对象：VideoUnmaskSwap、ButtonUnmaskSwap 取 `spawned_bins`，VideoRepick 取 `spawned_cubes`。同形按计划 3.1 口径逐盒 `np.array_equal` 比较 `half`、`local_p`、`local_q`；等高比较各对象初始世界 z，reset 完成后再读一次。GPU0 单进程约 3 分钟，未改仓库源码。

判定行：`SWAP_PREMISE=INFO seeds=30 not_same_shape=0 not_same_height=0`。VideoUnmaskSwap 与 ButtonUnmaskSwap 每对象 6 个盒体、z 全为 0.052 m；VideoRepick 每对象 1 个盒体、z 全为 0.020 m；逐盒最大偏差 0.0；`_load_scene` 时点的 z 与预扫 `slots` 逐个一致，reset 后高度同样全等。每个任务 30 个 seed 之间只出现一种盒体组合。被口径 B 剔除的 ButtonUnmaskSwap 10500、VideoRepick 10000/10400 同样满足两项前提。进程在汇总行和 JSON 写出之后以 139 退出（解释器关闭阶段段错误），30 行数据完整，原始输出见 [`records/swap_premise.txt`](records/swap_premise.txt)、[`records/swap_premise.json`](records/swap_premise.json)（sha256 前缀 `78a35b3fc30c3ab0`，24325 字节）。

该结果只说明当前 30 个母 seed 上「不同形或不等高」分支不会被触发，不代替用户对 K7 与 3.1 冲突的裁决。
