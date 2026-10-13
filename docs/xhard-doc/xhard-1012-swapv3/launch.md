# 交换配对 v3：阶段 0 至 C 启动档案

本档案记录已批准计划的代码、CPU 验证、GPU 契约及四卡冒烟；全量一百八十卡尚未获本轮起跑决定，须冒烟通过后另行报批。当前只完成开工审查与前置准备，不能报告生成验收通过。

## 用户决策与版本

关键用户消息按顺序原话保留：

1. `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-min3kinds-v3-plan.html 开始执行`
2. `错流的视频你可以保存 你只需不记任务成功即可`
3. `同意 继续`

第三条批准完整修订计划 `1012-swap-min3kinds-v3-plan.html @ b8d7d451fbf689ba0008bb5d9a8e97459f25dbd9`。本次重新开工由独立 `gpt-6.1-sol` 审查全文，无待裁决项：

```text
PLAN_CONSISTENCY_REVIEW=PASS base=b8d7d451fbf689ba0008bb5d9a8e97459f25dbd9 findings=0 blocking=0
```

先前冲突与用户裁决留在 [开工审查记录](records/start-consistency-review.md)，旧锚点的 FAIL 不能算作本版结论。失败视频可以生成、保存作证据；失败卡保持实际 `task_success=0`，真实账本字段不改，视频存在或视频工具 PASS 不代表任务成功，批次验收失败仍为 FAIL。

代码子任务 W1 从上述批准提交建立独立工作树 `/home/hongzefu/.codex/remote-control-host/worktrees/swapv3-w1/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `codex/swapv3-w1`。只允许计划指定七个文件，两个 `sub/V3-A` 与 `sub/V3-B` 提交经独立审查后，由主会话整合；其他四个原有工作树不动。GPU 与冒烟只能从整合、验证、推送后的干净主检出启动，实际完整 HEAD 作为运行器必填参数，并写入每份日志 `SOURCE_HEAD=`，与参数逐字核对。

## 环境、数据与产物边界

运行位置为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，sled-vail 环境 B。分支、远端、四个 SSH 别名、NFS、本机盘、两张 RTX 6000 Ada、micromamba 与 uv 符合规则。全局 `[agents] max_concurrent_threads_per_session = 32` 已存在，当前任务实际宿主容量为十六个子代理加主代理，未宣称三十二个并发实测。生成与验证固定 GPU0，不上集群；前置只读查询为 1286 MiB / 46068 MiB，未被占满，不干预其他任务进程。

复用本仓库 uv 管理的 `.venv`，不改依赖；`UV_CACHE_DIR=/home/hongzefu/.cache/uv` 显式设置。editable 校验实测为本仓库 `src/robomme/__init__.py`。工作树测试另设 `UV_PROJECT_ENVIRONMENT=<主检出>/.venv` 与 `PYTHONPATH=<工作树>/src`，不在工作树创建产物或 `.venv`。

旧根 `artifacts/xhard/xhard-1012-swapv2/` 只读，标记在新根 `.v2_mark`；起始 719 文件，标记后更新数 0。旧全量母清单不改，冒烟清单 `artifacts/xhard/xhard-1012-swapv3/smoke_seeds.json` 从原条目复制，四卡按官网顺序为：

|编号|任务|母 episode / seed|xhard20 预期|
|---|---|---|---|
|2.3|VideoUnmaskSwap|7 / 5700|成功，规划按 K5 与 v2 同卡相等|
|2.3|VideoUnmaskSwap|15 / 6500|graph 阶段，可行槽对不足 2/3|
|2.4|ButtonUnmaskSwap|15 / 8500|graph 阶段，可行槽对不足 2/3|
|3.2|VideoRepick|18 / 10800|graph 阶段，可行槽对不足 2/3|

只读重算 v2 全量确认：`V2_BASELINE_PREFLIGHT=PASS cards=180 ok=160 expected_plan_cards=105 new_reject_seeds=6`，详情在新根 `preflight.json`。第一条人工统计误把布尔邻接矩阵当邻居列表，导致自身断言退出 1，未写文件；回读既有 `graph_edges` 接口后重读通过，未发生生成故障，未修改判据。

## 验证顺序与完整命令

顺序为 W1 定向 CPU 验证 → 固定 BASE/TIP 的独立合并前审查 → 主会话整合与核心验证 → GPU 契约十九项及两个受影响节点 → 四卡单 worker 冒烟。任何失败按计划保存证据、找原因、作一次独立对抗核查、交用户；不换 seed、不改判据、不自行进入下一验证阶段。

W1 定向 CPU 验证及只收集 GPU 用例：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/.venv PYTHONPATH=<工作树>/src timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_plan.py src/robomme_xhard/tests/test_swap_v2_report.py src/robomme_xhard/tests/test_s2_configs.py -m 'not gpu' -q
UV_CACHE_DIR=/home/hongzefu/.cache/uv UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/.venv PYTHONPATH=<工作树>/src uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py src/robomme_xhard/tests/test_fatal_catch.py -m gpu --collect-only -q
```

主检出核心短测按 FAILED 节点集合比较，原基线四项不扩大为放行新失败：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest tests/lightweight/ src/robomme_xhard/tests -m 'not gpu and not slow' -q -rf
```

GPU 运行器内依次执行：

```bash
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 XHARD_TIMING_EVIDENCE_ROOT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/gpu-contract timeout 3600s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py src/robomme_xhard/tests/test_fatal_catch.py -m gpu -q -rf -rP -x
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 900s uv run --no-sync python -m pytest 'src/robomme_xhard/tests/test_s2_configs.py::test_gym_make_reset_contract[VideoRepick-xhard12]' 'src/robomme_xhard/tests/test_s2_configs.py::test_gym_make_reset_contract[VideoRepick-xhard20]' -q -rf
```

冒烟运行器内执行：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 1800s uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --env VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick --difficulty xhard20 --mother-manifest artifacts/xhard/xhard-1012-swapv3/smoke_seeds.json --gpus 0 --workers 1 --output-dir artifacts/xhard/xhard-1012-swapv3/smoke
```

上述命令只由运行器执行，不在前台重复起跑。两个唯一启动命令为：

```bash
tmux new-session -d -s xh-swapv3-gpu-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/run_gpu.sh <实际启动完整HEAD>"
tmux new-session -d -s xh-swapv3-smoke-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/run_smoke.sh <实际启动完整HEAD>"
```

运行器先核对 HEAD、干净工作区、日志与目标新鲜性。`set -o pipefail`、`PYTHONUNBUFFERED=1`、`tee` 与 `EXIT_CODE=` 记录保留。GPU 预算为十九项一小时、S2 两项十五分钟；冒烟预算三十分钟。四卡冒烟预期退出码 1，仅因三张正常任务拒绝；是否通过仍以账本、任务成功字段与判定行决定，基础设施故障不能算作正常剔除。

## 会话、日志与留档

本轮预定会话清单仅 `xh-swapv3-gpu-1012`、`xh-swapv3-smoke-1012`，按顺序启动，尚未实际起跑。运行代理只启动确定版本与命令，监听、预算与清理归主会话；不干预其他会话，不使用全局清理。日志分别为 `artifacts/logs/xh-swapv3-gpu-1012.log` 与 `artifacts/logs/xh-swapv3-smoke-1012.log`；GPU 时间步证据、新冒烟产物都落 `artifacts/xhard/xhard-1012-swapv3/`。

运行器 SHA256：`run_gpu.sh` 为 `7ff3285d37be52bff5076764375b5b25fb28265143e7c950bfd83ed6c3fa38ab`，`run_smoke.sh` 为 `2a24bebd6509a311551dded1541c03e9142f9d0490b687e1b7fc09c950376ff8`。运行器仅存于 `artifacts/`，本档案不复制 bash 或 yaml。

主会话用持久流式日志读取，逐级行缓冲，关注 passed、failed、ERROR、Traceback、BrokenProcessPool、svulkan2、EXIT_CODE 与生成成功/失败行。结束核对精确 tmux 会话与日志退出码；不新增高频 GPU 查询。日志清洗后置于 `records/`，核对完成和失败记录数量，结果另写 `result.md`，不把进行中状态写成完成。
