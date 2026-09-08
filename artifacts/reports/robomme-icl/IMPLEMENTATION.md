# robomme-ICL 实施与验证记录

## 授权范围与来源

用户批准新增并列的 `src/robomme_icl`，共享原有依赖环境，只完成四任务 joint_angle。原版 `src/robomme`、旧生成器、metadata、回放入口不修改。初始 Git 提交为 `1143477cba681bbb803b52324828634719a3f5a0`，原版源码树为 `1d0154117e58c783cd3466dbad910aeaaff573a8`。

首批要求每任务24条、三档各8条。次数与位置使用独立config，生成新seed，固定软件和设备下逐位复现。容器和藏块都保留，中央box减薄为30mm。候选搜索不得降低任务次数、跳出位置层或放宽碰撞要求。

## 环境与依赖

仓库位于本机NVMe/ext4的 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，预检剩余约2.8TiB，两张RTX6000 Ada，驱动570.211.01。`uv sync --locked --extra dev` 成功安装锁定的111个包，约48秒；Python3.11.14、torch2.9.1、ManiSkill固定Git提交 `07be6fbc66350ddca200abfb0a11b692f078f7fd`、SAPIEN3.0.2、mplib0.1.1。

Panda资产随锁定包位于仓库内 `.venv`，GPU0原生渲染检查通过；不读取NFS。全部新缓存、日志、生成数据均位于仓库内。

## 实现与修正

- 新版四类直接继承 `ICLBaseEnv(BaseEnv)`，注册独立namespace。原版工具调用集中于 `legacy_bridge`，纯config/清单编译不导入仿真库。
- 两份JSON配置、联合次数配额、分层布局和不可变 `EpisodeSpec` 已实现；目标角色与位置随机域分开，拒绝候选不更换seed或次数。
- 容器使用与视觉一致的compound碰撞形状；几何检查使用OBB及连续运动上界，物理子步再核查实际接触和kinematic物体几何。
- 四任务使用独立观测状态机；语言、目标、次数和判定来自同一spec。成功必须没有历史失败，演示不累计评测次数。
- HDF5保存完整spec、原始图像、状态、动作、阶段和事件。认证比较所有数值字节，并绑定源码、依赖锁与设备指纹。
- 密集位置初版独立轴排列产生同场小网格重叠，纯几何诊断只有86/96；改为约束分层匹配及原层内逐物体构造，没有扩大范围或放宽5mm要求。
- 补齐旋转物体真实角点的初始支持外框约束，发现7个VideoUnmaskSwap位置层/yaw层无交集；在规划阶段约束配对原层，保持各轴边际配额。候选只在原层与真实合法中心域的交集内采样，不裁边或跨层；支持外框只限制初始布局，不限制正常交换离开原窗口。
- 校正BinFill三档场景颜色1/2/3、hard目标2/3色；VideoUnmaskSwap三容器全占用、四容器一空；VideoRepick easy/medium同色、hard每色5块。
- 真实BinFill首次投放发生夹爪与孔板接触，改为在孔口上方释放，由真实入孔及落稳判定确认成功。
- RouteStick首次实跑cursor不推进，原因是把渲染标记z=.01当作棒端目标z，而实际棒端z=.07；改为统一XY触达与棒端高度范围，障碍扫掠和绕侧判定保留。
- VideoUnmaskSwap的第一次双进程认证失败，已定位到动画结束时遍历set导致动态解锁顺序变化，以及回采末帧物理位姿；改为稳定ID顺序和冻结端点。详细失败证据见 [独立报告](reproducibility_failure_vus_v1.md)，原始失败记录保留。

## 已执行验证

| 检查 | 命令或入口 | 结果 |
| --- | --- | --- |
| 新版轻量与导入隔离 | `uv run --no-sync python -m pytest tests/robomme_icl/ -q` | 修复后114 passed、4 skipped（需显式套件的GPU检查），36.14秒 |
| 旧版轻量测试 | `uv run --no-sync python -m pytest tests/lightweight/ -q` | 203 passed、2 skipped、4 failed，175.01秒；四失败见下文 |
| 打包 | `uv build --wheel --out-dir .cache/icl-wheel-v3` | 退出0；旧包102文件、新包31文件与源码逐字节一致；[报告](wheel-v3.json) |
| 修复后默认物体几何 | `uv run --no-sync python -m robomme_icl.suite.preflight` | 96/96，29.372秒，仅物体几何；[报告](geometry_preflight-v4.json) |
| 正式全量闭环 | `tests/robomme_icl/run_acceptance.py` | 96条认证、32/16-worker生成、断点、回放、连续reset全部通过；[最终报告](formal-v3/FINAL.md) |
| 首次双进程认证 | `prepare .../smoke-four-v1 --episodes-per-task 1 --workers 1` | BinFill638帧、RouteStick451帧严格一致；VideoUnmaskSwap位姿分叉，认证正确停止 |
| 动画确定性修复复测 | `prepare .../smoke-vus-v2 --tasks VideoUnmaskSwap --episodes-per-task 1 --workers 1` | 262帧两次独立进程逐位一致，退出0 |
| 开发版本四任务认证 | `prepare .../smoke-release --episodes-per-task 1 --workers 4` | 4/4：BinFill641、RouteStick451、VideoUnmaskSwap271、VideoRepick1045帧，全部双进程逐位一致 |
| 开发版本完整小样本验收 | `tests/robomme_icl/run_acceptance.py` 四个mode | generate逆序、replay、同环境reset、resume均4/4；[汇总](smoke_acceptance_release.json) |

旧版四项失败为 `test_TaskGoal` 中未知任务返回值、SwingXtimes连字符文本，以及 `test_step_error_handling` 中旧wrapper/旧replay的错误处理结构断言。它们检查的旧代码和测试文件均未修改；不扩大本轮范围修复旧版。完整原始输出在 `legacy-lightweight.log`。

## 当前状态

实现和全量验收已完成。基线 `e34474a6304b917b44cedae129ac621ddd52a430` 的96条规格完成两次独立物理进程认证、32/16-worker两轮全新生成、断点复用、回放和同环境连续reset，全部逐位通过。每遍63,689帧，两卡各绑定48条；详细命令、阶段退出码、HDF5及图表来源见 [FINAL.md](formal-v3/FINAL.md) 和 [FINAL.json](formal-v3/FINAL.json)。以下保留实施中的诊断与中断历史。

早期四mode组合验收超过了最初五分钟预估，各模式日志及结果均保留；后续完整运行均放入已登记tmux，从干净提交启动并写入完整退出状态。

首轮正式运行已从提交 `3e56b223607801ca0dd596dacbd17b4458d9981b` 启动，四任务基线 smoke 通过。随后默认96条已认证19条时，按用户新增的双GPU要求主动停止，完整套件未发布。旧记录保留于 `artifacts/generated/robomme-icl/validation24`，停止过程见 [stop_context.json](formal-v1/stop_context.json)。主日志 EXIT_CODE=0 来自退出trap，不能代替完整阶段成功证据。

首次提交前暂存检查发现 `io/__init__.py` 的多余文件末尾空行，移除后运行逻辑不变，但原始字节指纹按设计改变；后续已从新提交重新完成四任务最小认证及正式运行，没有绕过运行指纹。

## 双GPU并行改造

用户追加原话：“为什么不用2gpu尽可能并行生成？”当前改为 `--gpus 0,1 --workers 32`。每个seed按有序设备列表固定绑定GPU，每卡最多16个物理进程；候选搜索、HDF5读取和严格核对也移入独立进程，协调进程只接收摘要。物理仍为单环境CPU后端，双GPU分别承担对应记录的渲染。

认证指纹现在保存物理GPU编号、UUID和PCI地址；实际SAPIEN渲染设备必须与记录一致。生成、回放、reset和进程重试继承该绑定，不因worker数、运行顺序或空闲设备改变。禁止使用 `CUDA_VISIBLE_DEVICES` 重新映射；设备选择由 `--gpus` 显式控制。

双卡四任务 `prepare --episodes-per-task 1 --gpus 0,1 --workers 2 --max-candidates 64` 已退出0，目录为 `artifacts/generated/robomme-icl/dual-gpu-smoke`。BinFill641帧、VideoUnmaskSwap271帧在GPU0；RouteStick451帧、VideoRepick1045帧在GPU1。每条记录的两个独立物理进程逐位一致。`test_gpu_binding.py` 的三项真实设备检查全部通过，17.92秒；最终新版测试102 passed、4项需显式认证套件的检查skip，33.78秒。

双卡逆序4-worker生成、4-worker回放、逆序4-worker同环境双reset、1-worker断点复用均4/4通过，所有帧与认证逐位一致。四份总结位于 `artifacts/generated/robomme-icl/dual-gpu-acceptance/acceptance/`，日志为 `dual-gpu-{generate,replay,reset,resume}.log`。

`dual-gpu-smoke-samples.csv` 是500ms采样的局部40秒窗口，包含启动，不能用作稳态吞吐结论。正式双卡运行会记录完整资源曲线、每条轨迹的构建/执行/写入时间，以及CPU核数、存储介质、worker数和单episode batch size。

双卡正式运行从 `f2500c6fa91e9019e96aec819f4e08c2c9e5bbd9` 启动；随后因下述初始化边界需要修复而优雅中断，最终保留84条双进程认证，完整suite没有发布。记录位于 `artifacts/reports/robomme-icl/formal-dualgpu-v2/`，阶段和主日志退出码均130。

## BinFill初态与进入转换修复

一个已拒绝候选的方块初态完整在孔内，旧判定器会提前计数；后续oracle失败并不能替代初始化合法性检查。只读核对22个已完成第二次运行的BinFill spec，初态预填为0，不能推断旧84条中存在坏样本。具体坐标、候选哈希和检查范围见 [binfill_entry_guard.md](binfill_entry_guard.md)。

现在几何认证直接拒绝初始方块覆盖孔XY开口投影，包括悬在孔上方和动态物体的预定出现位置。判定器只在观察到活动方块完整处于孔外后，才允许它进入并落稳计数；停车不能提供资格，已投入方块停车后保留累计。初始孔内的方块必须真正移出再放回，不新增抓取历史条件。

优雅中断期间观察到Python3.11.14的 `max_tasks_per_child=1` 在worker退出后先补进程、再检查shutdown。原进程最终正常退出，不能称为永久死锁。外层纯CPU/I/O池改为复用worker、限制在途数量并显式取消未开始任务；每次物理仿真仍使用全新spawn进程。

新增负例及完整新版测试为114 passed、4 skipped，36.14秒；默认96个槽的新几何预检全部通过，29.372秒，配置哈希未变，报告见 [geometry_preflight-v4.json](geometry_preflight-v4.json)。`smoke-v3` 四任务各两次新进程均逐位一致，帧数仍为641、451、271、1045。

真实故障注入使用 `tests/robomme_icl/run_interruption.py --interrupt-after 12`：先在已启动GPU的子进程运行中施加超时，再由正式重试机制以同seed/spec/GPU恢复；271帧与认证一致，再次调用直接复用完整记录。[interruption-v3.json](interruption-v3.json) 保存两次尝试路径、固定身份和结果。新正式输出使用 `validation24-v3`，旧中断产物继续保留。

在单个pytest进程内依次运行四任务、跨两卡创建环境并各连续reset两次，显式 `ICL_TEST_SUITE=.../smoke-v3` 的四项真实检查全部通过，203.94秒。四个合法smoke的全部原始帧也与新增守卫前逐位一致；[valid_frames_v2_v3.json](valid_frames_v2_v3.json) 明确记录源码指纹不同，此对照不能替代新版本认证。

## 正式交付与使用

- 认证清单：`artifacts/generated/robomme-icl/validation24-v3/suite.json`，suite_hash 为 `e62bdd9e1dbe08d99d7e546c6412a2229848e16f45a34b543bdb3e17d68dc43d`；seed 为 `2000000000..2000000095`。
- 主数据：`artifacts/generated/robomme-icl/validation24-v3-verification/data/`；回放位于同根 `replay/`；16-worker对照使用独立 `validation24-v3-verification-w16/data/`。
- 两轮生成分别277.080秒与302.239秒，本次32-worker少用25.158秒；一次顺序对照不能证明全局最优，正式记录包含存储、设备、worker、采样、原始阶段时间及限制。
- 全量连续reset96/96通过，354.318秒；最终汇总重新核对五组签名验收记录、480个HDF5头、图表来源和当前运行指纹，退出0。工具为 `tests/robomme_icl/report_acceptance.py`，不会用HDF5头检查替代此前完整帧比较。
- `tests/robomme_icl/check_manifest.py` 独立确认454个完整物体支持框、1594个位置参数仍在原层、414个位置组/参数各层恰一次；最小物体净距5.010119mm；原版和锁文件共103文件、1796952字节对初始版本完全一致。[独立核对](formal-v3/manifest_check.json)。
- [BinFill实际配额与散点](formal-v3/figures/binfill.png)、[RouteStick实际配额与散点](formal-v3/figures/routestick.png)、[VideoUnmaskSwap实际配额与散点](formal-v3/figures/videounmaskswap.png)、[VideoRepick实际配额与散点](formal-v3/figures/videorepick.png)；四张正式图与预览字节一致，没有补造采样点。

新版的任务次数与位置在prepare时确定并冻结；正式运行以suite和seed定位spec及固定GPU，不重新随机抽样。使用入口和两份配置说明见 [源码包README](../../../src/robomme_icl/README.md)。原版四项既有轻量测试失败仍保留，不计为新版验收失败。
