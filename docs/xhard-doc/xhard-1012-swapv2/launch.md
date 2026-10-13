# 交换配对第二版：阶段零启动档案

本轮按 `1012-swap-pairing-v2-plan.html` 开工。阶段零在主检出冻结上一轮结果并预扫三十个母 seed；W1 在独立工作树按三个提交撤回、恢复判据、恢复工具。全量一百八十卡须在四卡冒烟后另行获批。

## 用户决策

1. 用户原话：「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-pairing-v2-plan.html 开工 有重大口径调整一律停工问用户」。
2. 档案名按东部开工日期固定为 `xhard-1012-swapv2`，旧目录 `artifacts/xhard/xhard-1012-coll/` 只读保留。

## 版本与环境

开工提交为 `a00efbe1c00569934f12f4dd398d2a8b0e20e118`，工作区干净；主机 `sled-vail`，两张 RTX 6000 Ada，生成使用 GPU0。GPU0 起跑前显存使用 1286 MiB / 46068 MiB，利用率 13%。SSH 别名符合环境 B，uv 与本仓库解释器可用，`robomme.__file__` 在本仓库 `src/`。并发配置为 32，本次宿主实际提供十六个子代理槽位。

扫描脚本随本档案提交，扫描启动时记录该提交。仅在 xhard 模块内替换规划器以捕获真实布局，不覆盖受保护的官方模块。每个母 seed 只 reset，不 rollout。先以一张卡验证脚本，再用同一版本预扫三十张，读取原有母 seed 清单，不生成新 seed。

阶段零单 seed 短测在脚本提交前执行（开工 HEAD 加本轮未提交扫描脚本，属于短测，不冒充干净 HEAD 运行）。VideoUnmaskSwap 5700 完成，`SWAP_V2_GRAPH_SCAN=INFO seeds=1 b_pass=1 b_reject=0 base_envelope_diff=0`，退出零。该任务没有按钮，`buttons=0` 不证明按钮读取已通过；三十 seed 正式预扫须验证另外两个任务的三个按钮。短测日志和 JSON 归档到 `records/`。冻结完成：`FREEZE=PASS files=426`、`EXIT_CODE=0`；另存字节数清单 `v1_coll_sizes.tsv`。

## 命令与产物

冻结会话 `xh-swapv2-freeze-1012`：对旧目录全部 426 个文件生成 `records/v1_coll_freeze.sha256`，成功后按已批准 U1 移除写权限。日志为 `artifacts/logs/xh-swapv2-freeze-1012.log`。旧目录无符号链接。完整文件哈希、文件数及结果将在阶段末核验。

```bash
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 uv run --no-sync python docs/xhard-doc/xhard-1012-swapv2/records/graph_scan.py --manifest docs/xhard-doc/xhard-1012-coll/records/mother_seeds_all.json --out artifacts/xhard/xhard-1012-swapv2/graph_scan_smoke.json --limit 1
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 uv run --no-sync python docs/xhard-doc/xhard-1012-swapv2/records/graph_scan.py --manifest docs/xhard-doc/xhard-1012-coll/records/mother_seeds_all.json --out artifacts/xhard/xhard-1012-swapv2/graph_scan.json
```

扫描会话预定 `xh-swapv2-scan-1012`，日志 `artifacts/logs/xh-swapv2-scan-1012.log`；采用 `set -o pipefail`、`tee`、`EXIT_CODE=`。失败不重试、不更换配置；按钮几何读取失败或口径 B 剔除超过六个时停下交用户。

## 代理与边界

W1 使用 `gpt-6.1-sol`，分支 `codex/swapv2-w1`，工作树 `/home/hongzefu/.codex/remote-control-host/worktrees/swapv2-w1/robomme_benchmark_newtask-v3-MotionJepa1006`。只写已批准 W1 文件集合，不 push、不合并主分支、不运行 GPU 任务。主会话负责冻结、预扫、资源、证据与整合。W2 待 W1 合并后派发。受保护目录 `src/robomme/` 始终零差异。

## 最新计划批准后的阶段 B 接续

用户本轮原话：「根据最新的计划修正后的内容 继续」。按最新 2.95.6 计划接续，批准基线为 `0dfb2aead0c48ad545909fa9280e64dfc3a1c404`，主工作区干净且已同步上游。C1 裁决为同形且等高，否则立即 `SceneGenerationError` 拒绝；C2 裁决为旁观物统一经 `bystander_states_of` 转换。既有 W1-d 已完成，阶段零、前提预扫不重跑；档案名仍为 `xhard-1012-swapv2`。

W2 使用 `gpt-6.1-sol`，独立工作树 `/home/hongzefu/.codex/remote-control-host/worktrees/swapv2-w2/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `codex/swapv2-w2`，从批准基线起顺序完成 W2-a/b/c。写入集合与计划分配表一致；不写官方源码、判据文件、已有工具、生成器、配置和依赖；不运行 GPU、不 push。独立审查复用原审查代理，主会话整合并验证。

为之后四卡 smoke 摘出母清单的四个原身份，写新根 `artifacts/xhard/xhard-1012-swapv2/smoke_seeds.json`：VideoUnmaskSwap 的 episode 7/seed 5700 与 episode 43/seed 9300、ButtonUnmaskSwap 的 episode 35/seed 10500、VideoRepick 的 episode 22/seed 11200。`SMOKE_MANIFEST=PASS cards=4`；仍未启动生成。GPU 契约的既有证据环境键 `XHARD_TIMING_EVIDENCE_ROOT` 将指向新根 `gpu-contract/`，不指向旧产物。

本轮开工核对 GPU0 显存 1286 MiB / 46068 MiB、利用率 12%，未被占满；SSH 别名与并发配置符合环境 B，配置 32、当前实际子代理槽位十六。实际 GPU 起跑前还须再次核对。重大口径调整立即停工；全量一百八十卡始终在四卡 smoke 后单独报批。
