# S4 xhard4 Vulkan 初始化故障：只读诊断

2026-09-26 18:32 EDT 现场核查；未新建占位作业、未调整 GPU 模式、未执行环境或重试、未终止任何进程。主代理已取消工作负载 step `61890468.10`，占位作业 `61890468` 保持运行。以下 GPU/内存数据全部是取消后的观测，不能倒推故障发生时峰值。

## 已证事实

- `sacct`：`61890468.10` 为 `CANCELLED by 114466650`，退出 `0:9`，耗时 `00:20:20`，MaxRSS `164776104K`（约157.1 GiB），作业申请192G；没有 `OUT_OF_MEMORY` 状态。主运行日志末行 `EXIT_CODE=137`。
- 节点 `gl1517.arc-ts.umich.edu`，NVIDIA A40，总显存46068 MiB，已用0 MiB、空闲45490 MiB，compute mode 为 `Default`，GPU util 0%，compute-apps为空；当前用户仅占位 `sleep infinity` 与本次只读命令，无生成worker残留。主机可用内存372710 MiB。
- 驱动595.71.05；ECC volatile 全零，无待处理行重映射、无重映射失败。aggregate DRAM correctable=2、correctable remapped rows=1属于累计计数，不能归因本次运行。
- xhard3 的 `round_00/results.json` 明确记录 `workers=16`，39/39成功。xhard4首轮同为16 worker，48条中26成功、2条InsertPeg任务失败、20条Vulkan初始化失败。因此“前三档rollout只有13worker，xhard4提升为16导致失败”不成立；13仅是抽签按任务数限制的worker数量。
- xhard4后续round_01～round_05各8条，全部 `RuntimeError`，共40条；runner的实际池大小为 `min(args.workers,len(jobs))`，这些轮次实际8worker，仍全部失败。round_06有8条jobs清单，取消时未写results，不能把这8条算成已知结果。
- Vulkan异常发生在 `train_split_worker.run_one` 的 `gym.make` 内，ManiSkill初始化reset的 `_setup_scene` 调用 `sapien.render.RenderSystem` 创建device时报 `vk::PhysicalDevice::createDeviceUnique: ErrorInitializationFailed`，尚未进入这些身份的任务演示执行。
- 成功xhard3与失败xhard4首轮均有16条 `Failed to find Vulkan ICD file` 警告，所以警告本身不能解释两者结果差异。两份runner日志都未出现 `out of memory` 文本。

## 未证边界

已定位到渲染device初始化层，底层根因尚未证实。没有故障当时的GPU显存/上下文连续采样；`dmesg` 返回权限拒绝，`journalctl -k`提示无系统日志权限，因而无法排除历史Xid或驱动故障，也不能声称已证明显存OOM。当前显存为空只证明取消后资源已释放，不证明再次创建Vulkan device可用。

本轮未运行Vulkan探针或任何环境，未调整worker或CPU渲染等配置；没有新的可用性/修复结论。

## 18:33 EDT 补充：确认故障时已进入独占模式

本节替代前述“仅知初始化失败”的诊断粒度，但不把触发机制猜测写成已证事实。

- round_01～round_05的runner.log各有8条svulkan2明确告警：`CUDA device 0 is in EXCLUSIVE or EXCLUSIVE_PROCESS mode`。首条为2026-09-26 18:29:23.009。成功xhard3与xhard4首轮没有该告警；首轮20次device创建失败依然存在。
- 经GreatLakes登录机再 `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes gl1517` 直接查询，**不另启srun**：18:33:21同一GPU UUID `GPU-dd2731bb-7405-64c2-6124-4487ab37cb31` 的模式确为 `Exclusive_Process`，显存仍0。未修改SSH配置、未接收新hostkey。
- 先前在 `srun --gpu_cmode=shared` 内测到 `Default`，该观测受步骤启动选项干预，不能代表步骤结束后的模式。只读命令通过srun执行仍可能改变设备模式；后续GPU观测改用登录机直接ssh节点。
- `scontrol show job -dd 61890468` 的原始SubmitLine**包含** `--gpu_cmode=shared`；batch脚本仅 `sleep infinity`。因此“hold提交时没有shared”已被排除。
- 时间关联：xhard4首轮jobs文件18:24:39.384写出，结果18:29:10.933写出；并发rsync步骤61890468.11和.12均在18:26:39启动并结束，落在首轮实跑期间。其后18:29:23开始新轮次明确报告独占模式。该时间线支持“短shared步骤结束后模式回退干扰长步骤”的假设，但没有GPU模式变更审计记录或站点hook源码，尚不能证明具体是哪一条步骤的退出触发；不为证实它而额外改模式或重跑环境。

修订结论：**Vulkan失败轮次遭遇独占GPU模式已证；独占模式的具体触发机制尚未完全证实。** 现有记录不支持将其归因为显存OOM或简单worker数量上升，也不支持通过关闭ray tracing等降级配置继续。

### 精确卡号与故障前后顺序

- 物理卡是Slurm GRES `IDX:1`、`nvidia-smi -q` 的 `Minor Number: 1`，对应 `/dev/nvidia1`；PCI `00000000:1E:00.0`，UUID如上。直接SSH会话被纳入 `/system.slice/slurmstepd.scope/job_61890468/step_extern/user/task_0`，仅可见获配卡，因而其 `nvidia-smi --query-gpu=index` 显示0是过滤后的逻辑序号，不是全节点物理卡0。
- 本机 `candidate-inputs/xhard3.jsonl` 的mtime为18:14:49.715581175，birth/ctime为18:26:39.607686215/18:26:39.614686208；`xhard4.jsonl` 的mtime为18:24:38.761045088，birth/ctime为18:26:39.646686174/18:26:39.653686167。rsync保留远端mtime，因此复制时间须看本机birth/ctime与sacct步骤时间，而不能误用mtime。
- `train_split_worker.run_one` 在 `gym.make` 前紧邻执行 `worker_dir.mkdir(exist_ok=False)`；20个首轮Vulkan失败身份均留下空目录，没有独立worker日志。最早失败身份StopCube/3目录时间18:27:00.453603114；StopCube/6为18:27:04.439646943，随后任务目录依次到VideoUnmaskSwap/6的18:27:30.951938468，全部晚于18:26:39的两次rsync步骤。
- 这些目录时间仅证明各失败身份在该时刻开始创建环境，**不是异常抛出的精确时间**。首轮runner只在汇总时打印无时间戳的失败行，无法恢复逐worker异常时刻。下一轮18:29:23.009明确独占告警是现存日志里最早的直接模式证据。
- 可复现的无srun查询：`ssh -o BatchMode=yes greatlakes 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes gl1517 "nvidia-smi --query-gpu=timestamp,index,uuid,pci.bus_id,compute_mode,memory.used --format=csv"'`。现场输出归档于 `gpu-direct-1834.txt`，步骤与本机文件时间分别在 `step-times.txt`、`candidate-times.txt`。

## 18:36 EDT 补充：调度收尾机制已复现，明确本次责任

主代理随后实施两组不创建环境的调度对照，两组均为 **0 reset、0轨迹**：

1. `mode-observer.log`：同一GPU的长shared观察步骤18:33:59～18:34:09持续读到Default；另一个shared短步骤18:34:10结束后，直接SSH于18:34:11读到Exclusive_Process，仍存活的长步骤18:34:14也读到Exclusive_Process，直到观察结束未恢复。
2. `mode-cpu-only-observer.log`：长shared观察步骤18:35:57起读到Default；18:36:10一个 `--gres=none` 的纯CPU短步骤结束后，18:36:12与18:36:15仍为Default。

由此确认本集群存在“并发shared短步骤收尾会把长步骤所用GPU切回独占”的调度行为。结合本轮rsync步骤18:26:39结束、随后20条初始化失败与后续40条独占警告，事故原因已收敛为**本轮代理把纯CPU候选回传也按shared GPU步骤执行，短步骤收尾干扰仍在生成的GPU上下文创建**。这是本轮运行编排错误，不应归咎于任务seed、环境本身、显存OOM或用户操作。旧脚本的准备与主代理运行时采用都属于本轮代理责任。

修复只改调用边界：`receive-seat.sh` 的目录存在检查和rsync、`hash-seat.sh` 的散列均改为 `srun --gres=none`，去除 `--gpu_cmode`；生成用的 `run-seat.sh` 保持shared。未修改生产环境源码、未关闭ray tracing、未在本次修复中重跑任何身份，也未停止正在进行的A席回传。用户尚未批准故障恢复预算时，不启动恢复。

教训：工具动作“只读”不代表调度动作无副作用。纯CPU的复制、散列、状态查询不得申请GPU；查询GPU状态优先直接SSH节点，避免由查询自身改变模式。并发步骤的启动与收尾都必须纳入共享GPU资源边界。

## A席回传脚本运行中被编辑：解析异常与责任

主代理后续确认：A席已经输出两档 `TRANSFER_DONE`，但 `receive-seat.sh` 末尾报 `line 32: f: command not found`，退出127。A席启动早于本轮将CPU步骤改为 `--gres=none` 的磁盘编辑；Bash并不保证启动时把整份脚本全部读入，文件长度变化影响尚未读取部分的偏移，导致末尾解析异常。因此“两档复制命令结束”不能改写为“整个回传脚本退出0”。

这是本轮代理对**正在执行的脚本作原地编辑**造成的第二项编排错误；不能以“已加载脚本不受影响”作为安全假设。主代理改以已有源清单逐档SHA校验确认复制内容，不自动重传、不覆盖已接收目录。B席于磁盘修改完成后启动，目前正在回传，现已冻结 `receive-seat.sh`、`hash-seat.sh` 及所有已启动的后处理脚本；后续任何修订必须使用新的版本路径，不能原地修改在跑文件。本次补记只写事故README，不再修改上述脚本。

## 恢复前未知轮次产物核验（未恢复）

使用 `srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=1 --gres=none` 纯CPU只读核验round_06清单的8个worker目录。八个目录全部存在但全部为空：HDF5=0、视频=0、spec_replay=0，未发现“已成功但取消前来不及写results”的完整产物；因此暂存恢复清单仍为76，不把任何未知身份额外认定成功。逐项记录在 `../recovery/round6-artifact-preflight.json`，命令退出0，未创建环境、未修改节点输出。

恢复名称已与询问用户的名称统一为 `v6-01-infra-recovery-01`；独立节点路径仍为 `/tmp/v6-s4-v6-01-infra-recovery-01`，名称字段与路径可不同。仍无批准文件、未执行恢复。准备脚本保留当前HEAD等于 `launch-commit.txt`、主仓clean及生产源码相对38488db不变的守卫；在途文档未提交前不能启动，不擅自放宽。

## 证据路径与只读入口

- `xhard3-rounds/round_00/{jobs.json,results.json,runner.log}`：成功对照。
- `xhard4-rounds/round_00`～`round_05` 的同名三文件：完整已结束轮次。
- `xhard4-rounds/round_06/jobs.json`：取消时未完成轮次，结果不存在。
- 主日志：上级 `logs/61890468.log`。

日志通过 `rsync -a --include='*/' --include=runner.log --include=results.json --include=jobs.json --exclude='*'` 与 `--rsync-path='srun --unbuffered --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=1 --gpu_cmode=shared rsync'` 从节点 `/tmp/v6-s4-v6-01/<tier>/rollout/run1/_rounds/` 复制，只读源头。元数据解析使用 `UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python`，未导入环境。
