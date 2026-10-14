# 八档循环本机冒烟与首次校验启动档案

本文件记录起跑当时的状态；已完成的实际结果见 [result.md](result.md)，不追溯改写启动口径。

本轮只执行已批准计划的本机阶段：先 VideoUnmaskSwap ep3 单 worker 一条，再 16 任务 ep0–7、32 worker 共 128 条；总共 129 个输出身份，不追加补跑。第二批含每任务每有效档第一条的 100 个校验样本。AWS 测速与 6400 条全量不在本机执行，仍由用户启动 AWS 后继续。

## 版本与代码状态

工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `newtask-v3-MotionJepa1006`，开工基线 `94c6a90b312c35ebf1a47940cd4d8159523212ce`。核心代码合入提交为 `f43d455dad054a4b4956a453f3b2eca1c13b5d99`，目录文档合入提交为 `1860bd8186be5c3d36a13555b6f2d24b5f8d65b4`；W1–W4、W6 的审查与实测见 [实施记录](implementation.md)。

本档先提交、推送，实际起跑完整提交号在起跑时写入本机 `artifacts/mixed8/launch_identity.json`，两份日志各写 `SOURCE_HEAD=`；结束后该不可由 Git 还原的起跑快照归入 `records/`。起跑时工作区须干净，两次冒烟期间不提交、更换代码或依赖。此批是冒烟诊断，正式全量的 Beta 锚点仍留在 AWS 全量前。

当前 `src/robomme/` 与 `src/robomme_xhard/{base.py,configs.py,envs/}` 相对开工基线零改动，`pyproject.toml`、`uv.lock` 未改；ManiSkill 锁定 `07be6fbc66350ddca200abfb0a11b692f078f7fd`。不修改录像器、planner、HDF5 写法或冻结配置。

## 启动与配置还原

命令从本机主检出运行，显式环境覆盖只有：

| 变量 | 值 | 用途 |
|---|---|---|
| `UV_CACHE_DIR` | `/home/hongzefu/.cache/uv` | 本仓库已声明的本机缓存位置 |
| `PYTHONUNBUFFERED` | `1` | 日志实时输出 |

生成参数为 `train` 布局、八档循环 `easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20`、`max-attempts=100`、GPU0。未覆盖的默认参数由源码锚点还原：限线程开启，`max_tasks_per_child=8`，`affinity=none`，`stop_on_pool_crash=False`，母清单参数全不设。失败按已批公式 `attempt+1` 推进；耗尽不补、不额外重跑。FailRecover 只给 11 任务的 base 档，以绝对 base 序号分配，首三条 z、再三条 xy；xhard 不设。

第一批完整命令：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --output-dir artifacts/mixed8/smoke1 --env VideoUnmaskSwap --episode-start 3 --episodes 1 --workers 1 --gpus 0 \
  --difficulty-cycle easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20 --max-attempts 100
```

第二批完整工作负载命令：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --output-dir artifacts/mixed8/smoke2 --env all --episodes 8 --workers 32 --gpus 0 --max-attempts 100 \
  --difficulty-cycle easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20
```

第二批用已核对的本机启动器，启动器只包上述命令、`SOURCE_HEAD`、`tee` 与退出码，不改变生成行为：

```bash
tmux new-session -d -s xh-mixed8-smoke2 "bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/mixed8/run_smoke2.sh"
```

启动器 SHA256 为 `36d0048bdd2ace6bae8323cb2d7b0775e677d0c38065de0de316942fff481450`，`bash -n` 退出 0；不在档案目录复制脚本。第一批预计约一分钟，直接运行并用同样的流式日志与退出码记录；第二批预计约十五分钟加重试，用 detached tmux。两批输出根起跑前均须不存在，不覆盖或清空旧产物。

## 数据与校验口径

生成使用公式 seed，不消费母清单、不下载数据。Golden 是进 Git 的 16 份原版 `episode_0` 结构 JSON，原版只读副本在 `/data/hongzefu/robomme_data_h5/`，revision `a5e4e25ffe8af34f64944f9533d06455ce5f8337`；本轮未做原版全文件 SHA256 复核。每任务有效循环取冻结配置键，缺档剔除，seed 的 `env_code` 原规范序不变。

第二批生成完成后，依计划执行独立身份对账与 `dump-subgoals`，交 W5 填充尚缺的规则。数量项冻结为 52 个 xhard 样本中的 80 项；不能数的项目必须具名交用户批准，不自动豁免、不缩应查集合。W5 合入与获批豁免完成后再做第一次正式 `check`，四条校验判定行完整报告，不因失败改文件、放宽阈值或启动 AWS。

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.check_mixed_h5 audit \
  --output-dir artifacts/mixed8/smoke2 --cycle easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20 \
  --episode-start 0 --episodes 8 --max-attempts 100
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.check_mixed_h5 dump-subgoals \
  --output-dir artifacts/mixed8/smoke2 --out artifacts/mixed8/smoke2/subgoals.json
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.check_mixed_h5 check \
  --output-dir artifacts/mixed8/smoke2 --golden-dir src/robomme_xhard/tools/golden_schema \
  --cycle easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20 --episodes 8 --workers 32 \
  --out-json artifacts/mixed8/smoke2/check.json --out-md artifacts/mixed8/smoke2/check.md
```

## 硬件与依赖

已核实 `sled-vail` 环境 B、32 核、内存 377 GiB；起跑准备时可用约 333 GiB。本机 `/data` 为 NVMe，剩余约 6.1 TB；GPU0 为 RTX 6000 Ada、46068 MiB，准备查询已用 1286 MiB、利用率 0%，另一用户进程只读不干预。正式起跑前复核 GPU0 未被占满，不自行换卡或上集群。

Editable 实测为本仓库 `src/robomme/__init__.py`；CPython 3.11.14，发行元数据版本 ManiSkill 3.0.0b21、SAPIEN 3.0.2、mplib 0.1.1、torch 2.9.1、numpy 1.26.4、h5py 3.15.1、psutil 7.2.2。复用既有 uv 虚拟环境，不安装或调整依赖。

## 会话、日志与起跑判据

本轮长任务 tmux 清单仅 `xh-mixed8-smoke2`。主会话唯一负责监听、资源与清理，其他现存会话一律不动。日志为 `artifacts/logs/mixed8-smoke1.log`、`artifacts/logs/mixed8-smoke2.log`；产物分别在 `artifacts/mixed8/smoke1/`、`artifacts/mixed8/smoke2/`。

第一批要求 `success_count=1`、H5 难度 xhard12、录像非空，成功结果带 `swap_plan`、`runtime_checks`、`xhard_knobs`，`recovery_mode=null`。失败先定位，按计划 G3 处置，不直接放大。第二批理想判据为 `SMOKE2=PASS requested=128 success=128 exhausted=0 z=33 xy=14`，实际任务成功由独立 `task_success` 字段报告；失败与耗尽如实列清单。

逐级行缓冲监听 `succeeded with seed`、`failed`、`进程池已损坏`、`ERROR:`、`Traceback`、`BrokenProcessPool`、`svulkan2`、`out of memory` 与 `EXIT_CODE=`。第二批最长等待 60 分钟，15 分钟无新 H5 或环境创建失败即留证报告，不擅自换 seed 清单、降级渲染、修冻结代码或重启补跑。结束核对精确 tmux 会话和日志退出码。

## 用户决策与留档

本轮关键原话：

1. 「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1013-mixed8-400ep-plan.html 开始实现 有问题问用户」。
2. W4 两轮仍失败后的裁决：「允许最小修复并增量重审（推荐）」。

其余已定口径原话保存在计划 K1–K18；尤其 K3 允许本计划公式 seed 换 attempt，K6 限本机实现与校验，K10 最大 100 次、耗尽不补，K14 具名豁免须批准，K16 首次校验无论结果完整报告、AWS 由用户启动。实施中停池补齐的对抗审查与原码反例见 [implementation.md](implementation.md)。

结束后 `result.md` 写实测与逐任务逐档尝试分布，`records/` 只放起跑快照、摘要／校验 JSON、身份对账及清洗日志等不可由 Git 还原的证据；不放 H5、视频、脚本或 YAML。清洗后 `EXIT_CODE=` 数量和值必须与原日志相同。以上是起跑记录，实际结果尚未产生。
