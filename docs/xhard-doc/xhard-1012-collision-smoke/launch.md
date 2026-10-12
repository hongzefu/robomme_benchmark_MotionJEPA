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

## 2026-10-12：方案 X 接续执行

用户本次原话：「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-collision-plan.html 按照最新计划 继续执行完」。本次沿用最新计划 K14 与 T1 的三文件范围：删除混入类的 `step` 覆写，改在 `_before_control_step` 复核段起点，零新增实例状态；端点四字段仍用 `np.array_equal` 精确比较，保留每个物理子步前后的检查。真实首探针失败即停止后续阶段，不换 seed、不重试、不放宽判据。

接续基线为 `b81a820f1c3e2ce93a4291e2666782f093320a63`，主检出与远端分支一致，工作区干净。环境核验为 sled-vail、两张 RTX 6000 Ada；实际只用 GPU0，初检 1286 MiB / 46068 MiB、利用率 0%，剩余磁盘约 6.4 TB。不安装或同步依赖；editable 导入分别落在本仓库 `src/robomme/` 与 `src/robomme_xhard/`。Codex 全局并发配置为 32，本会话宿主提供 16 个子代理槽位，未将配置值当作同时运行的实测。

改动前 CPU 核心短测命令为：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest tests/lightweight/ src/robomme_xhard/tests/ -m 'not gpu and not slow' -q
```

实测 375 项通过、4 项既有失败、2 项跳过、134 项排除，8.83 秒，pytest 退出 1。四项失败与用户此前批准保留的基线完全相同，日志为 `artifacts/logs/xh-coll-timing-baseline-cpu-1012.log`。后续整合必须精确保持该失败集合；新增失败或收集错误均不放行。

T1 在独立工作树 `codex/swap-timing-x` 上修改，使用 `gpt-6.1-sol`，独立静态审查同样使用 `gpt-6.1-sol`；探索使用 `gpt-6-luna`。代码代理不跑 GPU、不推送；主会话保留子提交并合并、复跑短测和推送，再从 clean HEAD 起跑。实际起跑的完整 SHA 与 porcelain 输出写入下面每份原始日志开头，结果归档时逐项列出该 SHA，不能把接续基线冒充运行版本。

GPU 顺序固定：

```bash
# 第一条：seed5700、xhard12，单任务单 episode，真实推进首起点及相邻共享端点。
CUDA_VISIBLE_DEVICES=0 XHARD_TIMING_EVIDENCE_ROOT=<本轮唯一JSON目录> UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py -q -s -m gpu -x -k 'test_real_step_first_start_and_shared_endpoint and VideoUnmaskSwap'
# 仅首探针通过后运行其余契约，排除刚通过的探针。
CUDA_VISIBLE_DEVICES=0 XHARD_TIMING_EVIDENCE_ROOT=<同轮JSON目录> UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py -q -s -m gpu -x -k 'not (test_real_step_first_start_and_shared_endpoint and VideoUnmaskSwap)'
# 仅真实契约全部通过后重测故障送达。
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 300s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_fatal_catch.py -q -s -m gpu -x
```

每条命令分别放入 detached tmux：`xh-coll-timing-probe-1012`、`xh-coll-timing-contract-1012`、`xh-coll-timing-d0-1012`，按实际启动登记，未启动的名字不属于清理清单。日志分别为 `artifacts/logs/<会话名>.log`，使用 `set -o pipefail`、`PYTHONUNBUFFERED=1`、`tee` 和 `EXIT_CODE=`；启动脚本只落 `artifacts/`，不复制进留档。主会话以精确 pane PID 流式监听，无自动重试。JSON 目录在起跑时选用全新的 `artifacts/tests/swap-timing/run-<时间戳>/`，在断言前保存全部数值。

仅以上闸门通过后，正常 smoke 沿用旧母清单 `docs/xhard-doc/xhard-1011/records/mother_seeds.json` 的 rank0：VideoUnmaskSwap seed5700/ep7、ButtonUnmaskSwap seed7700/ep7、VideoRepick seed13600/ep46，各一张 xhard20、GPU0、单 worker，新输出根为 `artifacts/xhard/xhard-1012-coll/timing-smoke/`，会话名为 `xh-coll-timing-smoke-<任务>`。阶段 E 清单的 VideoRepick 首 seed9600 属另一批次，不替换这三张 smoke 卡。

指定历史目录内没有找到三个 seed 的原始逐卡 `phases.solve_s`；旧批次在 sled-aspen、GPU0、12 worker 上运行，不能把计划旧文中的 44.1/47.8/72.5 秒称作 vail 实测。正常 smoke 完成后如实报告可获得的耗时和字节数。阶段 E 仍按计划 D6/P5，在具备 180 卡规模、实测耗时与磁盘报告后取得该批次决定；此前不自动启动全量。

本次实际起跑 SHA 为 `b7be8956e8399b33ea6fe7d889107f7a94e80ec8`（2.89），时间为 2026-10-12 17:56:49 EDT，porcelain 空。实际清单只有 `xh-coll-timing-probe-1012`，pane PID 3631415；原始日志 `artifacts/logs/xh-coll-timing-probe-1012.log`，JSON 根 `artifacts/tests/swap-timing/run-1791842209792896638/`。探针 14.94 秒退出 1 后停止，其他接续会话没有启动；版本、精确命令、完整数值与证据 SHA256 见 `result.md` 的最新接续结果。
