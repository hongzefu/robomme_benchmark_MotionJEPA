# 首次建场恢复验证通过，全量等待单独决定

首次建场按钮位姿修补、最小 GPU 节点、十九项 GPU 契约、两个 S2 节点及四卡冒烟全部通过。四卡实际为一成功、三张预期 graph 拒绝，基础设施故障为零；保留卡规划与 v2 对应卡结构及浮点均完全相同。全量一百八十卡尚未启动，仍须用户单独决定。

## 批准版本、代码与执行记录

用户关键原话依次为：“同意，改为核对首次建场的按钮位姿，保留9600和全部数值断言，先修订完整计划给我审查。”完整计划呈现后：“同意 继续执行”。批准版本为 `a34bb9d955d91f913b1ff696e47476c5b3a05b73`，独立开工审查 `PLAN_CONSISTENCY_REVIEW=PASS base=a34bb9d955d91f913b1ff696e47476c5b3a05b73 findings=1 blocking=0`；唯一 S2 命令序号文字在 `91fc0570` 统一，口径未变。

F1 子提交 `681dfcae82f459f69689811d980021d3341e7407` 仅修改指定测试函数三行：中文说明、每任务 `_make` 前清空捕获、去掉强制重建参数；7700／9600 和全部计算、数值断言、打印、清理原字节保留。独立代码审查通过，`--no-ff` 整合为 `0bf3a27ee8ada71822e3cf9d05daefd313b52c3e`（2.102.3），通过核心验证后立即推送。GPU 与冒烟均从该干净提交起跑，日志 `SOURCE_HEAD=` 精确命中，运行期间主会话未提交其他改动。

```text
BUTTON_FIX_SCOPE=PASS files=1 functions=1
BUTTON_ASSERTIONS_UNCHANGED=PASS seeds=7700,9600 buttons=3
PRE_MERGE_REVIEW=PASS base=91fc0570175129a7fa4d6eda3d05f0fe52968fc4 tip=681dfcae82f459f69689811d980021d3341e7407 files=1 commits=1 findings=0
CORE_SHORT=PASS new_failures=0 baseline_failures=4 passed=473 skipped=2 pytest_exit=1
SRC_ROBOMME_ZERO_DIFF=PASS base=5419e932
PRODUCTION_ZERO_DIFF=PASS base=c6d4780e
VENDOR_BYTES=PASS files=2
POST_MERGE_REVIEW=PASS merge=0bf3a27ee8ada71822e3cf9d05daefd313b52c3e tests=473_passed_4_baseline_failures files=1
```

主会话独立复跑工作树 CPU 三项通过、2.68 秒；GPU 仅收集十九项。整合后核心为 473 通过、原四失败、二跳过、137 排除，8.88 秒，退出码 1。四个 FAILED 节点与原基线完全一致，不称全仓零失败。

托管工作树工具无处理器，因此用 Git 建立同样隔离的 F1 工作树；整合推送后核对干净、只移除 F1 精确路径并安全删除专用分支，原四个工作树不动。该宿主工具差异不改变源码写集或测试语义。完整命令、资源与预算见 [本轮启动档案](firstbuild-launch.md)。

## GPU 三阶段实测

2026-10-13 00:10:09（美国东部时间）在 sled-vail GPU0 唯一启动 `xh-swapv3-gpu-firstbuild-1012`，前置版本、干净工作区、新日志、新证据目录、指纹与精确会话检查通过。主会话持续流式监听，无新增高频 GPU 采样。三阶段各运行一次，失败即停止的运行器未触发重试：

|阶段|实际通过数|pytest 耗时|退出码|
|---|---:|---:|---:|
|按钮位姿最小节点|1（两任务、三按钮）|8.01 秒|0|
|十九项完整契约|19，三项 CPU 用例排除|243.26 秒|0|
|VideoRepick S2 两节点|2|6.03 秒|0|

```text
BUTTON_POSE_LOADTIME=PASS buttons=3 max_dp_m=0 max_angle_rad=4.4408920985e-16
BUTTON_FIRST_BUILD=PASS cases=1 buttons=3 failed=0 skipped=0
XHARD_GPU_CONTRACT=PASS cases=19 failed=0 skipped=0
S2_GPU_VIDEOREPICK=PASS cases=2 failed=0
EXIT_CODE=0
```

三个 pytest 实测耗时合计 257.30 秒；各自预算 280／3600／900 秒，合计上限 4780 秒。位置误差为零、角误差约 `4.44e-16` 弧度，全部原 `1e-6` 断言满足，没有放宽。

故障送达用例原有入口还输出 `XHARD_FATAL_CATCH=PASS tasks=3 hang=0`，其原生证据在 `artifacts/tests/fatal-catch/run-1791864744189796369/`，同属本仓库产物根 `artifacts/`；如实保留该程序产物位置，不声称所有测试产物只写在新 GPU 证据目录。新时间步证据与三阶段日志在 `artifacts/xhard/xhard-1012-swapv3/gpu-contract-firstbuild/`，旧失败目录及 281 个证据文件未覆盖。

## 四卡冒烟实测与独立账本核对

GPU 三阶段通过后，00:15:47 在同一 GPU0、同一干净提交唯一启动 `xh-swapv3-smoke-1012`。原四条母样本清单、xhard20、单 worker、attempt=0，没有补 seed、换 seed 或为任务拒绝重试。实际生成总耗时 112.8 秒，峰值 RSS 4885.7 MB：

|官网编号|任务|母 episode／seed|实际 task_success|实际结果|
|---|---|---|---:|---|
|2.3|VideoUnmaskSwap|7／5700|1|成功，871 步；单卡 102.665 秒|
|2.3|VideoUnmaskSwap|15／6500|0|graph，`min_pair_kinds`，2/3；2.463 秒|
|2.4|ButtonUnmaskSwap|15／8500|0|graph，`min_pair_kinds`，2/3；2.919 秒|
|3.2|VideoRepick|18／10800|0|graph，`min_pair_kinds`，2/3；0.910 秒|

主会话独立读取四卡账本，核对身份集合、attempt、成功字段、失败类别、阶段、detail、JSON 边证据。保留卡与 v2 全量同身份规划比较，除新增 `graph.feasible_edges` 外原有结构和浮点字段一致，新增边集与邻接矩阵一致，实际最大浮点差为 0（批准阈值仍是 `1e-9` 米）。账本分类调用已实现的 `swap_v2_report::classify`，确认三张均为任务拒绝，infra／unknown 为零：

```text
SWAP_V3_SMOKE=PASS cards=4 reject_kinds=3 kept=1 plan_diff=0 max_float_delta=0.0
SMOKE_ACCOUNTING=PASS cards=4 ok=1 task_reject=3 infra=0 unknown=0
V2_ROOT_UNTOUCHED=PASS files=719 newer=0
EXIT_CODE=1
```

最后一行是生成器对三张正常拒绝的预期退出码，不是基础设施故障。成功 H5 为 `artifacts/xhard/xhard-1012-swapv3/smoke/xhard20/hdf5_files/VideoUnmaskSwap_ep7_seed5700.h5`，大小 580650224 字节。失败卡 task_success 如实为 0，没有因为输出日志或视频而变成成功。

可复现核对命令为 `UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python artifacts/xhard/xhard-1012-swapv3/validate_smoke.py`，本次退出 0；观察器排他创建结果文件，重复检查应只读已归档 JSON，不覆盖本轮结果。分类与时长汇总在 `records/smoke_outcomes.json`，逐卡拒绝证据与规划比较在 `records/smoke_validation.json`。

## 留档、限制与下一步

两份运行会话均正常结束，精确 `tmux has-session` 返回 1；终止日志分别保留 `EXIT_CODE=0` 与 `EXIT_CODE=1`，未执行强杀或全局清理。旧 GPU FAIL 仍见 [原失败结果](result.md)，新 PASS 不改写其历史结论。

归档三份清洗日志与四个实测 JSON；去除 tqdm 中间态及行尾空白，保留关键结果和每份一个终止 EXIT_CODE，共三条。原始日志、H5、视频与时间步数据继续留 `artifacts/`，docs 零新增 bash/yaml，不归档数据集或权重。生成结束打印的汇总 JSON 较长，日志仍保留完整内容；导读只引用具名判据，不复述其运行期逐步证据。

本次证明首次场景的按钮位姿及所列契约成立，不证明私有 RNG 强制重建行为；一张 smoke 规划完全相同不替代全量一百零五张规划验收。全量预期仍为现有三十个母 seed、母档加五档、GPU0／32 worker、一百八十卡，预计一百三十成功、五十正常拒绝、infra=0；约十分钟生成加五分钟包装是 v2 实测参考，不是本次全量实测。

下一步只向用户报批该全量。用户明确决定后才写 full-launch、打 2.103Beta 并起跑，期间冻结 HEAD；本轮没有启动全量或六列视频包装，没有将预期数字写成已交付结果。
