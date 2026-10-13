# v3 开工前计划一致性审查

本报告锚定 `AUDIT_BASE=2910e8cf387e8351d18059c6bceaa8f730c13ba3`，只审该提交中的 `1012-swap-min3kinds-v3-plan.html` 与必要源码。发起时工作区干净；未执行测试、生成或包装命令。

用户指令原话：`/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-min3kinds-v3-plan.html 开始执行`。

环境判定为 sled-vail 环境 B：仓库路径、分支及远端符合规则；NFS、本机盘与 SSH 配置存在，四个 SSH 别名与环境表一致；两张 RTX 6000 Ada，micromamba 与 uv 可用。全局 `[agents] max_concurrent_threads_per_session = 32` 已存在，无需修改；当前宿主实际容量为主代理加十六个子代理，未实测三十二个并发。GPU0 只读查询显示 1286 MiB / 46068 MiB，利用率 0%，未操作占用进程。

## 独立审查与主会话复核

按第 2 条派一个 `gpt-6.1-sol` 独立只读审查代理，在开工提交上审计划全文。其判定原文为：

```text
PLAN_CONSISTENCY_REVIEW=FAIL base=2910e8cf387e8351d18059c6bceaa8f730c13ba3 findings=1 blocking=1
```

唯一阻塞项为包装时序冲突，主会话已逐条回原文确认：

1. 第一部分第五节失败处置要求“任何判定行 FAIL……停止后续正式交付步骤”，并明确“不做六列视频”。
2. 第二部分第四节阶段 D 的命令顺序却为 `summarize` → `episode_strip_video` → `swap_v2_report`；身份与规划的权威判定行只认最后一个工具输出。
3. 反例：全量数量正确但身份错留/错剔，或某张规划浮点差超过 `1e-9`，前两步仍可能正常执行；视频已经生成后，最后一步才发现 `V3_IDENTITY_MATCH` 或 `PLAN_UNCHANGED` 失败。原顺序无法保证失败批次不出视频。

独立审查未发现其他阻塞：四卡冒烟、全量另行报批、三十个母 seed 固定、基础设施有限恢复例外、七文件写集、十九加两项 GPU 验证、一百零五张规划及一百八十张身份匹配的口径一致。

## 候选处置与授权边界

最初候选处置是先执行 `summarize` 与 `swap_v2_report`，由主会话核对生成、身份与规划判据，通过后再执行 `episode_strip_video`。该候选未实施，用户随后作出不同裁决，见下节。

根据 `AGENTS.md` 第 2 条：“凡涉及失败处理、接口、范围或验收的冲突，不得自行选一边：一律停下交用户裁决，裁决后按上一项修订，再交用户审查。”因此停在阶段 0，未派 W1、未创建开发工作树、未改源码、未启动 GPU 契约、冒烟或全量、未触碰 v2 根。全量仍须在后续冒烟通过后单独获得用户决定。

## 对抗验证与用户裁决

主会话先形成上述归因，再交独立审查代理作一次反驳核查，其判定原文为：

```text
FAILURE_RCA_REVIEW=CONFIRMED findings=1
```

代理检查未找到等价预检：`episode_strip_video::main` 只接受新轮根、母清单与输出路径，直接调用 `render_all`，没有旧轮根，不能作跨轮身份或规划比较；`summarize` 的 `net_identity` 只统计单条规划置换，不能替代 `V3_IDENTITY_MATCH` 与 `PLAN_UNCHANGED`。主会话回读固定提交中的两个工具核实，命令退出码为 0。这是尚未实施的计划冲突，不是已发生的运行事故。

用户随后原话：“错流的视频你可以保存 你只需不记任务成功即可”。因此本轮修订选择保留原包装顺序，允许失败批次生成与保存视频作为证据；失败卡保持实际 `task_success=0`，不改原账本的真实成功字段；视频存在或视频工具打印 PASS 不能替代任务成功，任何验收失败的批次总状态仍为 FAIL。

该裁决已统一写入计划引言、用户原话、K16、失败处置、阶段 D 闸门、runbook 与留档纪律。阈值、seed、代码写集、GPU 验证、全量报批、根因调查与对抗验证流程不变，SVG 未修改。完整修订计划交用户重新审查与批准后才继续；修订期间不另派重复计划审查，重新开工时再审批准版本。

## 证据读取与验证

可复现读取：

```bash
git show 2910e8cf387e8351d18059c6bceaa8f730c13ba3:1012-swap-min3kinds-v3-plan.html
git show 2910e8cf387e8351d18059c6bceaa8f730c13ba3:src/robomme_xhard/tools/swap_v2_report.py
```

以上只读命令退出码为 0；核对锚点为“第一部分第五节失败处置”与“第二部分第四节阶段 D”。本轮动态验证未开始，不能报告代码或生成验证通过。
