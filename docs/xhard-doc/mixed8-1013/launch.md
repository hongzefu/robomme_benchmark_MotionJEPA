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

---

# AWS 环境 C：接入、测速与全量起跑档案（2026-10-14 追加）

以上为 vail 本机阶段的起跑记录，原文不改；本节在 AWS 全量起跑前写入，并随 `2.131Beta` 提交，起跑时 HEAD 即该提交。

## 用户本轮指令原话

1. 「这台机器是 AWS p4de，是仓库 AGENTS.md 第 0 条的「环境 C」。先 clone（GitHub 必须用 ~/.ssh/id_ed25519_hongzefu，不要创建 ~/.ssh/config）……然后在仓库目录里重开会话，完整读 AGENTS.md、CLAUDE.md 与计划 1013-mixed8-400ep-plan.html，从计划 3.5 与 runbook R-4 ③ 起一路做完 R-1、R-5、R-6、R-7：环境 C 判定、uv sync、渲染探针、smoke 一、内存探针与 L32/L64/L96 测速、Beta commit、全量 6400 条、第二次校验与留档。本轮改口径：Beta commit、留档 docs/xhard-doc/mixed8-1013/ 的补写与 push 都直接在这台机器上做，不再回 vail；push 走 SSH key，不用 gh。缓存全部放 /scratch/hongze/.cache 下。全量起跑前核对 /scratch 空闲 ≥ 3.2 TB（按 vail 实测直线外推约 3.1 TB），不够就停下问我放哪。不改 src/robomme/ 与任何代码；测速与全量之间若发现需要改代码，停下问我。」
2. 「/scratch 可用空间从 2.9T 涨到 3.4T（占用率 51%），超过了你要的 3.2T。完成后可开始全量。」
3. 「不用用户在再等用户的审批了直接开始全量。」
4. 「VSCode这个可以删除。然后9月13号这个也可以删除」「其他的你可以自己判断。」（指测速期间争用驱动锁的两个外部 nvidia-smi 进程）

## 环境 C 接入（计划 3.5、R-4 ③）

- 第 0 条判定逐行与环境 C 列一致：主机 `ip-10-242-11-177.us-west-2.compute.internal`；NFS 与 `/data/hongzefu` 不存在；`/scratch/hongze` 存在；`~/.ssh/config` 不存在；8 × A100-SXM4-80GB（起跑前全空闲）；`nproc=96`、内存 1121 GiB；NUMA node0 = CPU 0–23,48–71、node1 = CPU 24–47,72–95。另有 micromamba（判据表未列，不构成冲突）、uv 0.12.2，无 gh。
- 仓库按用户原话直接 clone 分支 `newtask-v3-MotionJepa1006`（非 detached），HEAD `ea7cb1bbd85873a45bc2b12cbfd45e87500036cb`（2.130），`core.sshCommand` 固定 `~/.ssh/id_ed25519_hongzefu`。
- `uv sync --frozen --extra dev` 52 秒；解释器为 uv managed CPython 3.11.15（`/scratch/hongze/.cache/uv-python/`；vail 为 3.11.14）；ManiSkill 3.0.0b21、SAPIEN 3.0.2、mplib 0.1.1、torch 2.9.1、numpy 1.26.4、h5py 3.15.1、psutil 7.2.2，与 vail 相同；editable 指向本仓库 `src/robomme/__init__.py`。
- 渲染探针 `sapien.Device('cuda')` → `0000:10:1c.0 True`；SAPIEN 告警找不到系统 libvulkan 与 `/usr/share/vulkan/icd.d`（本机 ICD 在 `/etc/vulkan/icd.d`），回落自带库与 ICD，渲染可用。
- `ENV_C=PASS host=ip-10-242-11-177 gpus=8 disk_free_tb=3.14 sha=ea7cb1bbd85873a45bc2b12cbfd45e87500036cb`（接入时 `/scratch` 空闲 3,143,264,960,512 字节；全量前复核见下）。
- `SMOKE1=PASS gym_id=VideoUnmaskSwapXHard difficulty=xhard12 timestep=525 seed=5300 attempt=0 task_success=1 elapsed_s=96.4`：与 vail 同身份同 seed 同 timestep 数；单条 worker 内 83.8 秒（vail 38.5 秒）。证据 `records/aws-smoke1-run-summary.json`、`records/aws-smoke1.summary.log`。
- 受保护目录：本轮基线 `ea7cb1bb`，`src/robomme/` 工作区零 diff；W7 对 `SwingXtimes.py`、`VideoRepick.py`、`VideoPlaceOrder.py` 的异常名遮盖修复（2.127）是用户 P1 逐文件批准的例外，因此以 vail 开工锚点 `94c6a90b` 为基线的 R-0b `PROTECTED` 比对会因这三处不等，这是已批准差异而非越界。

## 开工前计划一致性审查

`PLAN_CONSISTENCY_REVIEW=FAIL base=ea7cb1bbd85873a45bc2b12cbfd45e87500036cb findings=10 blocking=4`（一个只读 sonnet 子代理）。主会话逐条核实后处置：R-4 ③／R-1 的「目录不存在」报告来自子代理看到的已执行现场，非计划冲突；磁盘以用户本轮 ≥ 3.2 TB 原话为准；R-7 的 `$C` 未定义按全循环串直写；PARTIAL 与 G7 仅在耗尽时触发，届时按 G7 报告；第二次校验输出改名 `check-aws-full.*` 不覆盖 vail 首次校验；Beta／回写为 `2.131Beta`／`2.131`；缓存变量写入启动器；跨机器对拍样本本机不存在，按 K7 只报数、记为不可得。均为文字统一或现场事实，不改口径，未派调整审查。

## 内存探针与测速（R-5）

tmux `xh-mixed8-calib`，启动器 `artifacts/mixed8/run_calib.sh`（SHA256 `28caf674d02ba1228a03972aa751de37a5a2721d162e78e62a25f57452226b2a`），`SOURCE_HEAD=ea7cb1bb`、`DIRTY=0`，01:21:33 → 02:57:43 UTC，`EXIT_CODE=0`。命令即计划 R-5 原文（`--root artifacts/mixed8/calib --env all --episode-start 0 --episodes 24 --max-attempts 100 --affinity per-gpu --difficulty-cycle <八档> --probe P8:8:0:on --probe-env <8 任务> --probe-episode-start 6 --probe-episodes 2 --cells 'L32:32:0,4,1,5:on;L64:64:0,1,4,5,2,3,6,7:on;L96:96:0,1,4,5,2,3,6,7:on' --mem-guard-gb 40 --mem-margin 1.2 --cell-timeout-min 90`）。

```text
MEM_PROBE=PASS peak_rss_gb=8.28681640625 peak_vram_gb=0.7874755859375 mem_avail_gb=1067.5172424316406
CALIB=PASS probe_rss_gb=8.28681640625 probe_vram_gb=0.7874755859375 cells_run=3 skipped=none best_workers=64 crashed_at=none
```

| 档 | workers | 卡序 | 成功／请求 | 稳态吞吐（条/分） | 稳态平均单条 wall_s | CPU 均值 | load1 均值 | GPU 利用率均值 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| L32 | 32 | 0,4,1,5 | 384/384 | 17.07 | 100.8 | 21.5% | 32.5 | 约 12% |
| L64 | 64 | 0,1,4,5,2,3,6,7 | 384/384 | 17.80 | 186.9 | 24.4% | 66.8 | 约 6% |
| L96 | 96 | 0,1,4,5,2,3,6,7 | 384/384 | 17.03 | — | 25.9% | — | 约 5% |

W* 按计划 3.4 取「稳态吞吐 ≥ 最高值 97% 的最小 worker 数」：17.80 × 0.97 = 17.26，L32 不达，**W\*=64，GPUS\*=0,1,4,5,2,3,6,7**。三档吞吐基本持平、单条耗时随 worker 数近乎线性变长、CPU 约 75% 空闲，说明存在与 worker 数无关的全局串行瓶颈；smoke 二唯一耗尽的 VideoPlaceOrder ep3 在三档测速中均成功（W7 修复后）。

监控干扰（正本第 16 条）：L96 起跑阶段 `vmstat` 见 CPU 97% 空闲、零磁盘 I/O、95 个 D 状态进程，全部为 nvidia-smi 卡在驱动锁（`os_acquire_rwlock_write／read`、`os_acquire_semaphore`）；负载下单次 `nvidia-smi` 8.9–13.5 秒（持久模式已开）。来源：①每个 worker `import sapien` 时 `sapien/_vulkan_tricks.py` 的 `_ensure_vulkan_icd`、`_ensure_egl_icd` 各调用一次 `os.system("nvidia-smi > /dev/null 2>&1")`，且 `DEFAULT_MAX_TASKS_PER_CHILD=8` 使 worker 反复重建；②VS Code 终端 pts/20 的 `watch -n 1 nvidia-smi`（01:31:50 起）；③9 月 13 日遗留、输出写入已删除文件的 `nvidia-smi --query-gpu=timestamp,… -l 1`（PID 2902609，工作目录 `/scratch/hongze/MotionJEPA`）；④测速自身的单个持久 `-lms 500` 采样器。经用户批准约 02:35 UTC 精确终止②（PID 903556）与③（PID 2902609），删后核对仅余④。因此 L32、L64 全程、L96 前约 10 分钟受②③干扰，三档条件不完全一致。主会话曾提出用 PATH 垫片让 ① 的 `nvidia-smi` 直接返回 0（零代码、只改环境），用户未作答；按用户「不用再等审批直接开始全量」，全量**不加垫片**，与测速条件同。

## 全量起跑（R-6）

- 输出 `artifacts/mixed8/full`（起跑前不存在）；日志 `artifacts/logs/mixed8-full.log`；tmux 会话清单仅 `xh-mixed8-full-1014`（本轮先前的 `xh-mixed8-calib` 已正常结束）；其他既有会话（`0`、`1`、`claude-private`、`codex`、`codex-repo`、`codex2`）一律不动。
- 启动器 `artifacts/mixed8/run_full.sh`（SHA256 `a02f0b66fd456840808c7ef40a7071804adea1a54ca34ce6a2d470002a96c311`），只包下列命令、缓存变量、`SOURCE_HEAD`、`tee` 与退出码，不在档案目录复制脚本：

```bash
tmux new-session -d -s xh-mixed8-full-1014 "bash /scratch/hongze/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/mixed8/run_full.sh"
# 启动器内的工作负载命令：
uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --output-dir artifacts/mixed8/full --env all --episodes 400 --workers 64 --gpus 0,1,4,5,2,3,6,7 --affinity per-gpu \
  --difficulty-cycle easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20 --max-attempts 100
```

| 环境变量覆盖 | 值 |
|---|---|
| `UV_CACHE_DIR` | `/scratch/hongze/.cache/uv` |
| `UV_PYTHON_INSTALL_DIR` | `/scratch/hongze/.cache/uv-python` |
| `MS_ASSET_DIR` | `/scratch/hongze/.cache/maniskill` |
| `XDG_CACHE_HOME` | `/scratch/hongze/.cache` |
| `HF_HOME` | `/scratch/hongze/.cache/huggingface` |
| `TORCH_HOME` | `/scratch/hongze/.cache/torch` |
| `PYTHONUNBUFFERED` | `1` |

- 未覆盖默认值：`train` 布局、限线程开启、`max_tasks_per_child=8`、`--stop-on-pool-crash` 关闭、母清单参数不设；公式 seed，任务性失败 `attempt+1`，上限 100，耗尽不补不换（K10、R3）。
- 磁盘：用户清理后 `/scratch` 空闲 3,725,991,100,416 字节（约 3.73 TB，df 51%），满足用户 ≥ 3.2 TB；主会话按 vail 首档样本 timestep 加权估全量约 4.39 M timestep × 0.667 MB ≈ 2.93–2.95 TB（含视频）。
- 预计耗时：按 W* 稳态 17.8 条/分约 6 小时，外加尾部拖尾。
- 盯盘：Monitor 过滤 `succeeded with seed` 以外的 `EXIT_CODE=|failed|进程池已损坏|ERROR:|Traceback|BrokenProcessPool|svulkan2|out of memory|NO RECORD`；30 分钟无新 H5 即报告用户；另观察 `/scratch` 余量。
- 起跑到第二次校验与留档完成之间不 commit（R6）；跑完回写同号 `2.131`。
