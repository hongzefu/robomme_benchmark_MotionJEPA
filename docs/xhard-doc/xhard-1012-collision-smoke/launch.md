# 交换碰撞 GPU 闸门与单卡冒烟启动记录

用户原话：「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-collision-plan.html 同意开工」；核心短测裁决：「采用基线对照闸门，保留这 4 项失败」。实施范围为既有计划阶段 A–D；180 卡全量阶段 E 不在本次起跑中。

## 版本、环境与资源

代码提交为 `20838a33`（2.82，全部实现整合），起跑前本留档先提交推送；实际启动时完整 HEAD 与 porcelain 在终端核对，记录于运行日志。主检出 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，当前工作区干净。固定判据来源与全部开发末端提交见同目录 `result.md`，依赖仍用既有 `pyproject.toml` / `uv.lock` / 主 `.venv`，未同步或修改依赖。

运行位置 `sled-vail` 本机，GPU0 一张卡，1 个进程串行执行。起跑前实测 GPU0 为 1286 MiB / 46068 MiB、利用率 0%；可用磁盘约 6.4 TB。只查 GPU0，不新增高频 GPU 监控，不干预其他进程。GPU0 被他人占满则停下，不换卡。完整 worker 闸门最多 300 秒，不重试、不换 seed、不修改判据。

## 执行顺序与完整命令

首先执行 D0，测试按顺序串行调用三个真实 `_worker`：VideoUnmaskSwap seed5700/ep7、ButtonUnmaskSwap seed7700/ep7、VideoRepick seed13600/ep46，xhard20，attempt0。第一张即失败时断言终止，不进入后续卡。测试进程仅将第二段起点复核替换为必拒并屏蔽其他运行期复核，reset 仍采用真实判据；该测试只证明 fatal 送达与失败产物保留，不能证明实际几何检查通过。

```bash
tmux new-session -d -s xh-coll-d0-1012 \
  "set -o pipefail; cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006; git rev-parse HEAD; git status --porcelain; PYTHONUNBUFFERED=1 UV_CACHE_DIR=/home/hongzefu/.cache/uv CUDA_VISIBLE_DEVICES=0 timeout 300s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_fatal_catch.py -q -s -m gpu -x 2>&1 | tee artifacts/logs/xh-coll-d0-1012.log; echo \"EXIT_CODE=\$?\" >> artifacts/logs/xh-coll-d0-1012.log"
```

起跑实际命令将版本两行也写入同一日志，测试命令与上述相同。结果根为 `artifacts/tests/fatal-catch/run-<纳秒时间>/`，每个任务有 `worker_result.json`，以及 `FAILED_` H5 / 视频。后续运行仅在前一道具名闸门通过后执行：GPU reset、五档前缀、真实第一段与相邻端点对齐、reset 拒绝及运行期不抛异常；再按计划每任务一张 xhard20、单 worker 正常生成冒烟。未通过则停，不以故障注入成功替代正常几何成功。

## 监听、判据与失败处置

实际启动清单：`xh-coll-d0-1012`（pane PID 3504414）、`xh-coll-gpu-contract-1012`（pane PID 3510094）。第二会话同样核 clean HEAD 后，用 `timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py -q -s -m gpu -x`，日志 `artifacts/logs/xh-coll-gpu-contract-1012.log`，环境变量同 D0。主会话通过每个会话精确 pane PID 的 `tail --pid=<PID> -F` 监听日志，关注 `XHARD_`、`FAILED`、异常与 `EXIT_CODE=`，不忙轮询，不全局清理 tmux。D0 已退出 0；真实契约已退出 1，后续正常冒烟会话没有启动。

- 起跑核对：HEAD 与已提交版本相同，porcelain 空；日志出现测试启动或第一条任务结果。
- D0 验收：`XHARD_FATAL_CATCH=PASS tasks=3 hang=0` 且 `EXIT_CODE=0`；GPU 使用只是设备与执行条件，独立任务成功字段仍按注入预期为 false。
- 上限：300 秒，超时退出 124 也算 FAIL，保留全部日志与已写产物，不自动重新起跑。
- 环境创建失败、正常判据拒绝或代码错误：保存版本、任务/seed、失败证据和退出码，停止后续阶段，先诊断。不得降级配置或换 seed 找成功。
- 本轮不提交任何集群作业，不启动全量生成；全量耗时与磁盘只有正常冒烟完成后才能实测报批。

## 留档与还原

运行结束后在 `result.md` 追加版本、退出码、各任务字段与未解决项，`records/` 仅归档原始结果与清洗日志，不复制启动脚本、配置、checkpoint 或数据集。运行命令来自本文件；源码可用固定提交的 `git show <起跑提交>:src/robomme_xhard/tests/test_fatal_catch.py` 与生成器同提交还原。
