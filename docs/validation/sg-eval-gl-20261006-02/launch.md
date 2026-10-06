# sg-eval-gl-20261006-02 起跑档案（launch）

第二阶段：六条新接口路线直出官方版式视频 + 统一逐步记录，GL A40 上跑第一、二、三档。权威计划：
[`docs/plans/1005-eval-video-phase2-all-models-rerun-plan.md`](../../plans/1005-eval-video-phase2-all-models-rerun-plan.md)。
本文件按正本第 12 条两段式的第一段写（版本与代码状态、启动与配置还原），随批次推进逐节追加；跑完另写 `result.md` 与 `records/`。

## ① 目的与授权

- 用户开工令（2026-10-06 02:2x EDT）：「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/docs/plans/1005-eval-video-phase2-all-models-rerun-plan.md 开始执行 有问题半小时内问用户 尽可能不要阻塞 一口气做完再让用户判断」。
- 此前已批（计划文首与六节）：开工后无人值守跑到计划结束、不设截止、≤10 卡、占位 job 自管；预算轨迹 6366（硬）、reset 计量 14143、账本软上限约 141430（「Reset额度可以。提高到现在的十倍左右不用作为硬边界。」）；Astra 本机 smoke ≤2 局、5 美元硬上限（「唯一需要注意的就是astra还是只跑两次。」）；集群操作预授权。

## ② 版本与代码状态

| 项 | 值 |
|---|---|
| 工作副本 | `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9` |
| 开工时 HEAD | `3f5237797d644211cf17ed9245c8b96f42bcd7a0`（12.474） |
| BASE（S0 提交后） | `b869a3df9e7406b8f5458697f22656165b9c50b3`（12.475） |
| 回放工具 | `ba1bbb06`（12.476，`client_replay_eq.py`） |
| 第一档执行副本 | `$N/robomme_benchmark-noise` 检出 `b869a3df`（clean；`uv.lock` 与此前 `f8f76fba` 零 diff，借用其 `.venv`） |
| 原侧补跑执行副本 | `$N/robomme_benchmark-sgeval` HEAD `a299fcdcd8d8664a07bff758011d7ea7ca899f55`（上一轮冻结，不同步、不改；链脚本起跑断言 HEAD 与 clean） |
| SimpleMemVLA 原版工作树 | `$N/SimpleMemVLA-official-xhard0`（`git -C $N/SimpleMemVLA worktree add --detach … 4e0c04f`），clean |
| MME 原版克隆 | `$N/robomme_policy_learning-official-xhard0`，分支 `official-xhard0-0929` = `927c56d9879762c1afa0217d79a591093c9ffbe9`；子模块 `third_party/robomme_benchmark` = `856bc3a189d4172f3f47dbee4424d585f8d78db3`（本地克隆源 `/data/hongzefu/robomme_benchmark_MotionJEPA`，仅在该克隆里覆盖子模块 URL），其 `src/robomme` 与本仓库 `diff -rq` 为空 |

`$N` = `/nfs/turbo/coe-chaijy-unreplicated/hongzefu`；本轮 NFS stage `R2=$N/sgeval-20261006-02`（`scripts/`、`logs/`、`inputs/`、各档目录）。

## ③ 占位 job 与席位

| JobID | 名称 | 节点 | 本轮用途 |
|---|---|---|---|
| 63188711 | sgev-hold-00 | gl1525 | 批次 1 第一档（V9 → xhard0 串行） |
| 63188712 | sgev-hold-01 | gl1512 | 批次 1 PonderPounce 原侧 shard-01（96 局，席 11） |
| 63188713 | sgev-hold-02 | gl1513 | 批次 1 QwenVL 原侧 shard-01（38 局，席 21） |
| 63188714 | sgev-hold-03 | gl1518 | 批次 1 QwenVL 原侧 shard-02（38 局，席 22） |
| 63188715 | sgev-hold-04 | gl1503 | 批次 1 QwenVL 原侧 shard-03（39 局，席 23） |
| 63188716 | sgev-hold-05 | gl1527 | 批次 1 QwenVL 原侧 shard-04（38 局，席 24） |
| 63188719 | sgev-hold-06 | gl1525 | 空闲（留给批次 2） |
| 63188720、63325534、63325535 | sgev-hold-07～09 | PENDING（AssocGrpGRES） | 排到后用于后续批次 |

清单文件 `$N/gl-hold-logs/hold-jobs-sgeval-20261004.txt`；收尾按清单逐个 `scancel`。

## ④ 批次 1（2026-10-06 02:36 EDT 起跑）

登录节点 `gl-login3` tmux（本轮会话清单，清理只按此清单）：`p2-g1`、`p2-pp-s11`、`p2-qw-s21`、`p2-qw-s22`、`p2-qw-s23`、`p2-qw-s24`。

```bash
R=$N/sgeval-20261006-02; I=$N/sgeval-20261004/inputs
tmux new-session -d -s p2-g1 "bash $R/scripts/launch_seat.sh 63188711 gate1 $R/scripts/chain_gate1.sh"
tmux new-session -d -s p2-pp-s11 "bash $R/scripts/launch_seat.sh 63188712 orig-pp-s11 $R/scripts/chain_orig.sh --seat 11 --model pp --shard $I/pp/gate2/shard-01.json"
# 席 21～24 ↔ 63188713～16 ↔ QwenVL shard-01～04
tmux new-session -d -s p2-qw-s2$i "bash $R/scripts/launch_seat.sh <job> orig-qwenvl-s2$i $R/scripts/chain_orig.sh --seat 2$i --model qwenvl --shard $I/qwenvl/gate2/shard-0$i.json"
```

- 第一档：`$R/scripts/gate1_pass.sh`（照抄上一轮 `sgeval-20261004/scripts/gate1_pass.sh`，执行副本换成 `robomme_benchmark-noise@b869a3df`）——`hard_parity.py generate --expect-ref scripts/configs/noise-ref-20261003.json`，V9 `--side H2 --tier v9`（43 格 × 3 局 = 129）、xhard0 `--side H --tier xhard0`（16 任务 × 3 局 = 48），各 4 worker；`noise_run.py ship --finalize` 回 `$R/gate1/g1-new-{v9,x0}`；`noise_gate.py gen-regress check` 出 `GEN_REGRESS=`。
- 原侧补跑：`$R/scripts/chain_orig.sh` → `run_official_hard.sh --dataset test-hard0 --max-steps 1300 --gpu 0 --infra-retry-budget 3`（QwenVL 另 `--episode-wall 3600`、`SEAT_XLA_MEM_FRACTION=0.65`），stage `$R/gate2-orig-{qwenvl,pp}`。环境变量照抄上一轮 `seat_chain_v2.sh`。
- 补集合核对（起跑前）：上一轮 QwenVL 原侧非 infra 结果 39 局恰为 shard-00（与 shard-01～04 交集 0）；PonderPounce 96 局恰为 shard-00（与 shard-01 交集 0）。本轮补跑集合 = QwenVL 38+38+39+38 = 153、PonderPounce 96。

## ⑤ 代码改动（子代理分工）

S0（主会话，12.475）；S2a、S2b、S8、S1、S6、S7、S4、S5、S3 九个 opus 写入型子代理于 BASE 同时派出，按 S2a → S2b → S8 → S1 → S6 → S7 → S4 → S5 → S3 逐个合并（合并记录随合并追加到本节）。
