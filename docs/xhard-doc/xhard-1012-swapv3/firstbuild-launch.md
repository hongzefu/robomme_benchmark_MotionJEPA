# 首次建场按钮位姿修补：恢复验证启动档案

本轮从已批准完整计划 `a34bb9d955d91f913b1ff696e47476c5b3a05b73` 恢复。只修指定测试函数的捕获与建场时序，保留 seed、全部计算和数值断言；依次执行最小按钮用例、十九项 GPU 契约、两个 S2 节点、四卡冒烟。全量仍须冒烟通过后另获用户决定。

## 用户原话、审查与代码状态

用户先要求：“同意，改为核对首次建场的按钮位姿，保留9600和全部数值断言，先修订完整计划给我审查。”完整 HTML 已提交并呈现，随后用户原话：“同意 继续执行”。

独立 `gpt-6.1-sol`、中等推理强度代理审批准提交全文：

```text
PLAN_CONSISTENCY_REVIEW=PASS base=a34bb9d955d91f913b1ff696e47476c5b3a05b73 findings=1 blocking=0
```

主会话核实唯一文字序号漏项后统一“S2 为运行器第三条 pytest（阶段 B 的第二项）”，提交 `91fc0570175129a7fa4d6eda3d05f0fe52968fc4`，机制、范围和判据未变。F1 以该提交为 BASE，源码仍是 `c6d4780e` 的失败版，只允许 `test_swap_collision_gpu.py::test_button_pose_loadtime_matches_initialized_geometry` 时序与中文说明。

托管工作树工具当前分别返回 `No handler registered for tool: codex_app.list_artifacts` 与 `No handler registered for tool: codex_app.create_worktree`。主会话改用 Git 创建同样隔离的独立工作树 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/.claude/worktrees/swapv3-firstbuild`，分支 `codex/swapv3-firstbuild`。原四个工作树不动，F1 禁写主检出，不 push、不跑 GPU。其提交经独立 R1 审查、主会话 `--no-ff` 整合、核心和冻结项验证后才 push。实际 GPU／冒烟版本取随后整合的干净 HEAD，作为运行器必填参数并写 `SOURCE_HEAD=`，不能用本档案尚在实施时的 HEAD 冒充实际运行版本。

## 环境、输入与资源

环境为 sled-vail 环境 B，两张 RTX 6000 Ada，NFS 与本机盘存在，SSH 四个别名与规则一致，uv/micromamba 可用。主检出路径和分支正确。全局 `[agents] max_concurrent_threads_per_session = 32` 已存在，当前宿主实际容量不等同于三十二个并发实测；所有新代理显式中等或更高推理强度。

固定本机 GPU0，前置查询为 1286 MiB / 46068 MiB，未占满；不干预其他任务、不新增高频 GPU 监控。显式 `UV_CACHE_DIR=/home/hongzefu/.cache/uv`，只用已有主 `.venv`、`uv run --no-sync`，不改依赖。

最小节点仍含 ButtonUnmaskSwap 7700 两按钮与 VideoRepick 9600 一按钮，合计三按钮。生成侧四卡冒烟清单已照抄原条目，按官网顺序为 VideoUnmaskSwap 5700／6500、ButtonUnmaskSwap 8500、VideoRepick 10800，档位 xhard20、单 worker、attempt=0。5700 须成功且规划按 K5 与 v2 同卡相等；另外三张须在 graph 阶段按 2/3 正常拒绝。

旧 `run_gpu.sh`、GPU 失败日志、281 个时间步证据、失败结果文档全部保留。旧 v2 根 719 文件、标记后更新 0；本轮保留原 `.v2_mark` 不 touch、不重置。

## 完整命令与预算

F1 在独立工作树只运行三项 CPU 接口短测与十九项收集；主会话整合后核心仍按原四个 FAILED 节点集合比较，不放行新增失败。详细 CPU 命令见批准 HTML 的阶段 A-F。

GPU 新运行器内部依次执行：

```bash
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 XHARD_TIMING_EVIDENCE_ROOT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/gpu-contract-firstbuild timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py::test_button_pose_loadtime_matches_initialized_geometry -m gpu -q -rf -rP -x
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 XHARD_TIMING_EVIDENCE_ROOT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/gpu-contract-firstbuild timeout 3600s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py src/robomme_xhard/tests/test_fatal_catch.py -m gpu -q -rf -rP -x
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 900s uv run --no-sync python -m pytest 'src/robomme_xhard/tests/test_s2_configs.py::test_gym_make_reset_contract[VideoRepick-xhard12]' 'src/robomme_xhard/tests/test_s2_configs.py::test_gym_make_reset_contract[VideoRepick-xhard20]' -q -rf
```

每阶段记退出码与单独阶段日志，只有退出零、通过数恰为 1／19／2、无 failed/skipped/xfail/xpass 才进入下一阶段；最小节点还须原 `BUTTON_POSE_LOADTIME=PASS buttons=3`。预算分别 280／3600／900 秒，合计上限 4780 秒，不含自动重试。运行器记录总 `EXIT_CODE=`，使用 pipefail、无缓冲输出与 tee。

唯一 GPU 启动命令：

```bash
tmux new-session -d -s xh-swapv3-gpu-firstbuild-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/run_gpu_firstbuild.sh <实际干净完整HEAD>"
```

新日志为 `artifacts/logs/xh-swapv3-gpu-firstbuild-1012.log`，新证据根为 `artifacts/xhard/xhard-1012-swapv3/gpu-contract-firstbuild/`；起跑前两者须不存在。新运行器 SHA256 为 `2b45a07322c25631cd048c740c33f0fea98ecaa3537091d65aa90b235b197a2a`，`bash -n` 退出零，不复制脚本进 docs。

GPU 三阶段全部通过后，才由运行代理另批执行四卡冒烟：

```bash
tmux new-session -d -s xh-swapv3-smoke-1012 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/xhard/xhard-1012-swapv3/run_smoke.sh <同一实际干净完整HEAD>"
```

其内部生成命令、四卡清单与输出路径见 [原启动档案](launch.md)，预算 1800 秒，输出 `artifacts/xhard/xhard-1012-swapv3/smoke/`、日志 `artifacts/logs/xh-swapv3-smoke-1012.log`，两者起跑前必须不存在；运行器 SHA256 仍为 `2a24bebd6509a311551dded1541c03e9142f9d0490b687e1b7fc09c950376ff8`。有三张正常拒绝，生成器退出码 1 属预期，只有账本与逐卡判据能决定验收。

## 会话归属、失败处理与收尾

本轮预定 tmux 仅 `xh-swapv3-gpu-firstbuild-1012`、`xh-swapv3-smoke-1012`，顺序启动。运行代理只启动确定版本与既有运行器，起跑后交回节点、时间、日志、SOURCE_HEAD 和精确会话回执；持续流式监听、预算与清理归主会话。不会操作用户或其他任务的 tmux。

失败立即停止后续阶段，保留证据、主会话只读定位、一次独立对抗验证、交用户；不换 seed、不重试、不放宽、不自行调整测试或生产机制。成功完成后，清洗日志与具名判定行写 `firstbuild-result.md` 和 `records/`，旧 `result.md` 的失败结论保留。首次场景通过不代表强制重建行为已验证；smoke 通过也不授权全量。
