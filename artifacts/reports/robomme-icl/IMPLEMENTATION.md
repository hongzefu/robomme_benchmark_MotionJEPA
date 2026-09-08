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
| 新版轻量与导入隔离 | `uv run --no-sync python -m pytest tests/robomme_icl/ -q` | 最终94 passed、4 skipped（需显式套件的GPU检查），15.32秒 |
| 旧版轻量测试 | `uv run --no-sync python -m pytest tests/lightweight/ -q` | 203 passed、2 skipped、4 failed，175.01秒；四失败见下文 |
| 打包 | `uv build --wheel --out-dir .cache/icl-wheel-check` | 退出0；打包范围包含新旧两个包 |
| 最终默认物体几何 | `uv run --no-sync python -m robomme_icl.suite.preflight` | 96/96，29.636秒，最小净距下界5.010mm，仅物体几何；[报告](geometry_preflight-v3.json) |
| 单条真实任务路径 | `oracle.run_episode` | 四任务分别成功；当前完整套件与多种复现条件继续验证 |
| 首次双进程认证 | `prepare .../smoke-four-v1 --episodes-per-task 1 --workers 1` | BinFill638帧、RouteStick451帧严格一致；VideoUnmaskSwap位姿分叉，认证正确停止 |
| 动画确定性修复复测 | `prepare .../smoke-vus-v2 --tasks VideoUnmaskSwap --episodes-per-task 1 --workers 1` | 262帧两次独立进程逐位一致，退出0 |
| 当前源码四任务认证 | `prepare .../smoke-release --episodes-per-task 1 --workers 4` | 4/4：BinFill641、RouteStick451、VideoUnmaskSwap271、VideoRepick1045帧，全部双进程逐位一致 |
| 当前源码完整小样本验收 | `tests/robomme_icl/run_acceptance.py` 四个mode | generate逆序、replay、同环境reset、resume均4/4；[汇总](smoke_acceptance_release.json) |

旧版四项失败为 `test_TaskGoal` 中未知任务返回值、SwingXtimes连字符文本，以及 `test_step_error_handling` 中旧wrapper/旧replay的错误处理结构断言。它们检查的旧代码和测试文件均未修改；不扩大本轮范围修复旧版。完整原始输出在 `legacy-lightweight.log`。

## 当前状态

实现和四任务小样本闭环已完成，完整96条真实物理认证尚未完成。不能将几何96/96或单条成功当作全量物理、全量复现或全量回放通过。四mode组合验收超过了最初五分钟预估；各模式独立日志、当前源码指纹与完整结果均已保存，后续同类组合不再前台启动。

下一阶段以本轮已提交并推送的源码为基线，在 `gen-icl-cert96-20260907-v1` 会话中启动默认96条认证，套件目录为 `artifacts/generated/robomme-icl/validation24`；然后用已提交的 `run_acceptance.py` 执行跨调度生成、回放、reset和恢复。正式运行尚未启动，不能提前标为通过。

提交前暂存检查发现 `io/__init__.py` 的多余文件末尾空行，移除后运行逻辑不变，但原始字节指纹按设计改变；开发smoke仍保留为开发证据，正式会话会先从新提交重新完成四任务最小认证，再启动96条，不能绕过运行指纹。
