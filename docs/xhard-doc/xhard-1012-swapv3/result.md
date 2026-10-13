# 交换配对 v3：GPU 契约失败，停止在阶段 B

代码、CPU 验证与独立代码审查完成并推送；GPU 十九项契约未通过，后续 S2 两节点、四卡冒烟及全量均未启动。失败没有重试、没有换 seed、没有改阈值。建议与用户裁决见文末；本报告不能作为生成验收通过的证明。

## 用户原话与版本

本轮关键用户消息依次为：

1. `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-min3kinds-v3-plan.html 开始执行`
2. `错流的视频你可以保存 你只需不记任务成功即可`
3. `同意 继续`

第三条批准修订计划 `b8d7d451fbf689ba0008bb5d9a8e97459f25dbd9`；失败视频可以保存作证据，视频本身不能使失败任务变成成功。本轮 GPU 契约没有生成数据集视频，不为出视频补跑任何生成。

运行位置、完整命令、预算与环境见 [启动档案](launch.md)。源码合并提交及实际 GPU 启动版本为 `e39795183752f5afe0ddca2ecf77a95b0a8753f6`（2.102），启动工作区干净。W1 的两个功能提交 `2254eb9174f4009192f88b4f6e306b8e56faf9df`、`1aa330806d643e86d6b22d6d0f0ca442c6020bce` 与模块说明补齐提交 `6fc98d1394f41c30c156824795b551d6699e5bd0` 经 `--no-ff` 原样保留。文字补齐是唯一实施漏项，不改变机制或验收。

期间另一会话同步了 `23e8f6b732b46a7f8aa094808564659bf8a834b0`（2.101.8），仅修改 `AGENTS.md`，要求所有新子代理推理强度显式中等以上；本轮未改其内容。运行与失败审查代理均显式 `gpt-6.1-sol`、`reasoning_effort=medium`。实际源码与运行参数没有因此变化。

## 已完成的 CPU 与代码闸门

独立开工审查、七文件范围及合并前审查原文：

```text
PLAN_CONSISTENCY_REVIEW=PASS base=b8d7d451fbf689ba0008bb5d9a8e97459f25dbd9 findings=0 blocking=0
SCOPE=PASS files=7
SWAP_PLAN_V3_CPU=PASS failed=0
REPORT_V3_CPU=PASS failed=0
GPU_CONTRACT_COLLECTION=PASS cases=19
PRE_MERGE_REVIEW=PASS base=b8d7d451fbf689ba0008bb5d9a8e97459f25dbd9 tip=6fc98d1394f41c30c156824795b551d6699e5bd0 files=7 commits=3 findings=0
```

主会话独立复跑工作树定向 CPU 为 `151 passed, 8 deselected, 2 warnings in 2.98s`，退出码 0。整合后核心为 `4 failed, 473 passed, 2 skipped, 137 deselected, 2 warnings in 8.72s`，pytest 退出码 1；四个 FAILED 节点与计划指定原基线逐一完全相同，不用通过数掩盖失败：

```text
CORE_SHORT=PASS new_failures=0 baseline_failures=4 passed=473 skipped=2 pytest_exit=1
SRC_ROBOMME_ZERO_DIFF=PASS base=5419e932
VENDOR_BYTES=PASS files=2
POST_MERGE_REVIEW=PASS merge=e39795183752f5afe0ddca2ecf77a95b0a8753f6 tests=473_passed_4_baseline_failures files=7
V2_ROOT_UNTOUCHED=PASS files=719 newer=0
```

完整核心日志及节点列表分别在 `records/xh-swapv3-core-1012.summary.log` 和 `records/post_merge.json`。原源码、两份引入文件哈希均一致，整合已推送。W1 托管工作树已归档，专用分支安全删除；原四个工作树仍保留。

## GPU 唯一尝试与实际失败

2026-10-12 23:44:59（美国东部时间）在 sled-vail GPU0 由运行代理唯一启动 `xh-swapv3-gpu-1012`。前置 HEAD、干净工作区、新日志、新证据目录、运行器 SHA256 和精确会话名检查通过。日志 `SOURCE_HEAD=` 与实际运行提交一致，起跑交接后主会话用持久流式监听接管；未新增高频 GPU 查询。GPU0 起跑前 1286 MiB / 46068 MiB，未操作其他任务进程。

真实十九项契约命令为启动档案第一条 GPU pytest，带 `-x`；实测耗时 130.40 秒。结果为 `1 failed, 17 passed, 3 deselected, 236 warnings`，退出码 1，余下一项未执行；三项 deselected 为 CPU 用例，不算十九项中被跳过的用例。

```text
XHARD_GPU_CONTRACT=FAIL cases=19 passed=17 failed=1 not_run=1 exit=1 seconds=130.40
GPU_CONTRACT_EXIT_CODE=1
EXIT_CODE=1
S2_GPU_VIDEOREPICK=NOT_RUN cases=2
SWAP_V3_SMOKE=NOT_RUN cards=4
```

运行器在 GPU 契约失败后退出，未执行后续 S2 命令；精确 `tmux has-session -t '=xh-swapv3-gpu-1012'` 返回 1，任务已结束，无需强杀。没有冒烟或全量会话。主会话只保存证据，没有重新派运行命令。

失败节点为 `test_swap_collision_gpu.py::test_button_pose_loadtime_matches_initialized_geometry`。ButtonUnmaskSwap 7700 分支之后，VideoRepick 9600 的 `env.reset(seed=9600, options={"reconfigure": True})` 在建场认证阶段抛 `SwapCollisionError(stage="graph")`，没有进入该分支的真实按钮位姿断言。拒绝证据为：

```text
可行槽对不足=2/3
feasible_edges=[[0,2],[1,2]]
0-1 gap_m=-0.0007714178513457924，contact，中点 s=0.5
0-2 gap_m=0.05904029323411775
1-2 gap_m=0.062077976439141064
```

异常和图证据原文在 `records/xh-swapv3-gpu-1012.summary.log`，结构化提取在 `records/gpu_failure.json`。281 个已产生的时间步证据保留在 `artifacts/xhard/xhard-1012-swapv3/gpu-contract/`：按官网顺序为 VideoUnmaskSwap 115、ButtonUnmaskSwap 115、VideoRepick 51。没有删除产物，也没有把测试失败写成任务成功或正常全量交付。

## 根因与一次独立对抗核查

主会话只读定位：`VideoRepick::__init__` 创建并播种私有 `self.generator`，先抽重复次数和交换次数；`_load_scene` 再通过该生成器抽按钮、颜色、区域、旋转、方块及目标。首次 `gym.make` 已触发一次建场。强制 `reconfigure=True` 会再次调用 `_load_scene`，继续使用已推进的私有随机流。ManiSkill `BaseEnv.reset` 重建其自身的 main/episode 随机流及全局 Torch 状态，但没有重新播种或恢复 `VideoRepick.self.generator`；xhard 类也没有补这种重播。

因此“相同 seed 的强制第二次建场仍是同一场景”前提不成立。旧 v2 全量中 9600 首次建场三条边的间隙为 0.0553662513、0.0236523890、0.0216728755 米，只能支持首次场景通过，不能保证第二次建场仍通过。本次新闸门只读图，不消耗父类私有随机流，按两条边拒绝符合其批准口径。

主会话形成上述归因后，另派一个独立 `gpt-6.1-sol`、中等推理强度代理，只读固定源码、实际安装的 ManiSkill 与本次证据，尝试反驳、核查替代解释。其原文判定为：

```text
FAILURE_RCA_REVIEW=CONFIRMED findings=5
```

五项核查分别确认直接拒绝链、私有生成器未重播、闸门未改变父类随机流、缺乏本次 GPU/Vulkan 基础设施或按钮推导错误证据，以及归因边界。实际安装 `direct_url.json` 与冻结 `uv.lock` 均声明 ManiSkill 提交 `07be6fbc66350ddca200abfb0a11b692f078f7fd`。

边界：本次失败实例没有两次建场的完整槽位、形状与生成器状态快照，没有独立重算碰撞间隙；不能声称已逐值对拍具体几何变化，也不能声称碰撞算法整体或 VideoRepick 按钮推导已验证正确。源码和堆栈足以确认用例的重建前提错误，不用历史首次场景代替当前对照。

## 待用户裁决与留档范围

建议保持 9600 和全部位姿数值断言，将捕获清空放在首次 `gym.make` 之前，初始化后直接比较该首次建场的按钮位姿，不强制生成第二个随机场景。这样贴合正式生成的首次建场链路，但会取消该用例的第二次重建覆盖，属于测试时序变更，尚未改代码、未修订实施口径、未重新运行。

另一候选是保留强制重建，明确恢复“构造函数两次抽样之后、首次建场之前”的私有生成器状态；简单 `manual_seed(9600)` 不等价，而且可能掩盖连续重建行为。也未选择或实施。

按 `AGENTS.md` 第 2 条及批准计划第五节，先交用户裁决，完整修订计划并重新放行后才继续。不能自行改该测试、换 seed、放宽闸门或重试；当前总状态为阶段 B 失败、后续停止，全量仍未授权起跑。

本档案归档两份清洗日志与三个实测 JSON，均只保存 Git 不能还原的结果，不复制脚本、配置、权重或数据集。清洗日志另去除九处 pytest 输出行尾空白，内容与判定值不变，原始日志仍完整保留于 `artifacts/logs/`。每份清洗日志恰保留一个终止 `EXIT_CODE=`，共两条；运行器仍只在 `artifacts/`。旧 v2 根收官仍为 719 文件、标记后更新 0。
