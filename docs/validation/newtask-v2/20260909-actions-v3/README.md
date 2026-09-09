# schema 3 对象与动作冻结：完整五项对拍

状态：完成本轮五项对拍与补充回归；轻量全量测试的 4 个原基线既有失败单列。本轮重新生成 60 次，
原始和合并产物各完成 60 对严格比较，最终 852 张图版复核通过；没有用历史结果代替。

## 固定输入与实现

- 运行编号：`20260909-actions-v3`；原值基线：`94449db0a068a6b454b55a13ebd48f0394d89cc8`。
- 任务实现：`c56e5af`；观察器版本 3：`16f6e18`；新增消费位置 AST 校验：`3a59cd7`。
- 完整使用原 15 格 `cases.json`，A1/A2 原入口，B 不传配置，C 显式传 schema 3。
- 每格固定单 episode、单 worker、GPU 0、train、attempt 0、max-tasks-per-child 8。
- 配置和依赖没有变化；具体对象与路线由原随机调用、episode seed 和交换开始时状态确定。

配置快照及完整来源指纹见 [sampling_config.json](sampling_config.json)、
[context.json](context.json)；实际报告工具指纹见
[verification_context.json](verification_context.json)。固定 Python 3.11.14、Torch 2.9.1、
NumPy 1.26.4、SAPIEN 3.0.2、h5py 3.15.1，GPU 0 为 RTX 6000 Ada，驱动 570.211.01。
`uv.lock` SHA-256 为 `983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`，
配置 SHA-256 为 `8fae52b7cf20bfcdb71b0a8d6378924e423a0e66450d3d51f95e9a66aeccd2bc`。
60 条实际运行参数、GPU／线程绑定和 seed 见 [execution_records.json](execution_records.json)。

## 校准与中间运行

观察器版本 3 的四路 BinFill easy smoke 共 122.3 秒，全部首次成功且四对完整比较通过；
无观察器原版另重新生成一次，27.4 秒，与开启观察器的 HDF5 全字段差异 0。
111 项定向测试通过，5.09 秒；源码检查确认工作树及原基线 66 组操作元一致。

`20260909-actions-v2` 已产生 60 次轨迹、15 格比较及 852 张实际目视图版，但收尾发现
原观察器缺少随机调用前状态与全局 Torch 状态；其产物保留为中间证据。正式结论改用本
运行重新采集的完整随机证据。最终 PNG 与本轮已看图片的帧集合和 SHA-256 逐项一致时，
才绑定同一图像的目视结论；有差异的图片必须重新查看。

本轮最终出图已完成上述核验：全部新图与本轮实际查看的图片逐项相同。
正式目视来源为 `artifacts/review/20260909-actions-v2/<格>/manifest.json`，
最终 [visual_inspection.json](visual_inspection.json) 同时记录来源路径、来源散列、
每张最终图片散列和目视结论。`artifacts/review/20260909-actions-v3/` 中的准备画板
不是另一套已经独立查看的记录，不混淆两者。

生成前先完成原版开关校准，随后才开始本次 fresh 矩阵。首格 B 运行后补充了不在
B 路执行的 `_cross_check` 静态接入检查，C 启动前完成测试；期间只暂停编排父进程，
没有暂停物理轨迹。任务源码、随机调用和动作执行链保持不变，来源差别在 context 中留档。

## 15 格实测规模

全部 60 次均为 fresh，首次尝试成功；每路合计 8,739 个 HDF5 timestep、676 次
`torch.rand/randint/randperm` 调用。下表图版数包含每格的一张 reset 初态图。
原始与合并四对比较均已全部通过，完整生成编排耗时 2479.7 秒。

| 格 | episode / seed | HDF5 timestep | 随机调用 | 图版 |
| --- | --- | --- | --- | --- |
| `BinFill-easy-dynamicTrue` | 0 / 4000 | 550 | 44 | 43 |
| `BinFill-medium-dynamicTrue` | 2 / 4200 | 883 | 71 | 47 |
| `BinFill-hard-dynamicTrue` | 0 / 4000 | 943 | 91 | 56 |
| `BinFill-easy-dynamicFalse` | 1 / 4100 | 366 | 41 | 14 |
| `BinFill-medium-dynamicFalse` | 1 / 4100 | 549 | 83 | 20 |
| `BinFill-hard-dynamicFalse` | 1 / 4100 | 742 | 67 | 26 |
| `RouteStick-easy` | 0 / 16000 | 200 | 11 | 71 |
| `RouteStick-medium` | 0 / 16000 | 400 | 15 | 137 |
| `RouteStick-hard` | 0 / 16000 | 600 | 19 | 205 |
| `VideoUnmaskSwap-easy` | 0 / 5000 | 326 | 19 | 29 |
| `VideoUnmaskSwap-medium` | 0 / 5000 | 346 | 22 | 29 |
| `VideoUnmaskSwap-hard` | 0 / 5000 | 515 | 22 | 40 |
| `VideoRepick-easy` | 0 / 9000 | 756 | 20 | 50 |
| `VideoRepick-medium` | 0 / 9000 | 810 | 20 | 59 |
| `VideoRepick-hard` | 0 / 9000 | 753 | 131 | 26 |

## 已实测的具体对象与动作

以下取 A1，四路的结构化证据逐项相同。索引均从零开始；容器使用 `spawned_bins`，
方块使用 `spawned_cubes`，路线节点使用 `buttons_grid`。交换箭头左侧是发起对象，
右侧是交换开始时按实际位置选出的搭档，不能用颜色或名字代替索引。

| 任务 | 难度 | 实际抓取索引 | 按执行顺序的交换双方 |
| --- | --- | --- | --- |
| VideoUnmaskSwap | easy | `[2]`，藏绿色方块 | `1→2`、`2→1` |
| VideoUnmaskSwap | medium | `[1]`，藏红色方块 | `0→3`、`1→2` |
| VideoUnmaskSwap | hard | `[1,2]`，依次红、绿 | `0→3`、`1→2`、`3→0` |
| VideoRepick | easy | 始终为 `1`，任务索引 `0,6,8` | `1→2`、`2→1` |
| VideoRepick | medium | 始终为 `1`，任务索引 `0,7,9` | `1→2`、`2→1`、`0→2` |
| VideoRepick | hard | 始终为 `8`（`cube_red_2`），任务索引 `0,3,5` | 无；实际生成 15 块 |

VideoUnmaskSwap 的前三个交换调用窗口依次为 `64→114`、`114→164`、`164→214`；
VideoRepick 为 `200→250`、`250→300`、`300→350`，实际使用数量见表。
每个窗口的搭档首次确定步均等于该窗口起点。这些值来自实际 `swap_flat_two_lane`
调用证据，并非从初始化时含 `None` 的 schedule 推测。

| RouteStick 难度 | 完整节点序列 | 逐段方向 |
| --- | --- | --- |
| easy | `8→6→4` | 顺、顺 |
| medium | `8→6→4→2→0` | 逆、顺、逆、顺 |
| hard | `8→6→8→6→8→6→4` | 逆、顺、顺、顺、顺、逆 |

顺／逆分别对应 `clockwise`／`counterclockwise`。每段在演示和执行中都绑定同一目标
和 `expected_dir`；完整 task_index、对象名、阶段及方向见
[action_bindings.json](action_bindings.json)。
所有原始 HDF5 的关节动作、末端状态与双相机数据也参加逐位比较，不能仅凭节点表认定
实际运动一致。

## 五项验收与补充回归

| 项目 | 实测结论 | 轻量证据 |
| --- | --- | --- |
| ① 关键帧 | 15 格、837 张 HDF5 关键帧与 15 张 reset；无未出图的规定关键帧，机检差异为零；852 张全部完成本轮目视及最终散列绑定 | [keyframe_index.json](keyframe_index.json)、[visual_inspection.json](visual_inspection.json) |
| ② 状态与事件 | 构造、两次初始化、reset、每次 step 前后、对象位姿及事件四对一致；两个视频任务的抓取对象和实际交换双方、RouteStick 的节点与方向绑定一致 | [result.json](result.json)、[action_bindings.json](action_bindings.json)、[manifest.json](manifest.json) |
| ③ HDF5 | 原始与 15 格隔离合并产物各完成 60 对全字段比较，差异均为零；不以容器封装字节或视频编码字节作判据 | [result.json](result.json)、[merged_comparison.json](merged_comparison.json) |
| ④ 随机流 | 每路 676 次受监测调用的次序、参数、shape、dtype、源身份、结果、调用前后状态一致，未截断；NumPy 播种事件一致 | [action_bindings.json](action_bindings.json)、`evidence/` 中的逐段散列链 |
| ⑤ 连续 worker | 原版／默认／显式配置各真实执行 3 局；逐局与独立运行的 HDF5 和完整证据一致，配置不变，新环境缓存为空 | [worker_isolation_complete.json](worker_isolation_complete.json) |
| attempt 重试 | A1/B/C 均 seed 4000 失败、attempt 1 的 seed 4001 成功；失败类别及三对成功 HDF5 全字段一致 | [retry_comparison.json](retry_comparison.json) |
| 16 任务 | 显式配置 `--env all`，16/16 首次成功、0 exhausted，命令退出码 0，耗时 329.17 秒 | [all16_summary.json](all16_summary.json) |

连续 worker 的 PID 分别为原版 `825928`、默认 `827106`、显式配置 `828200`；每路
内部三局确实同 PID，分别耗时 85.96、85.90、85.89 秒。合并与隔离报告保存了两侧
完整数据的聚合指纹，可以离线重新推导相等，不能仅靠一个 passed 标记。

全部自动阶段的主日志为 `artifacts/logs/action-freeze-v3.log`，最终 `EXIT_CODE=0`。
60 次生成的完整命令、退出码见 [runner_report.json](runner_report.json)；
合并、隔离、重试、16 任务和出图的 68 条命令见
[supplementary_commands.json](supplementary_commands.json)。最终出图命令使用 `--limit 0`，
耗时 284.43 秒；最终目视复核另由 `parity_review finalize` 执行，退出码 0。

## 记录边界、失败与修正

- RouteStick 三格各有 48 条高亮事件落在原 `NO RECORD` 步；三路的清单和时序相同，
  完整状态和事件已比较，但原 HDF5 没有这些步的图像。不伪造目视结论、不平移配帧；
  它们在关键帧索引的 `event_record_mapping.unrecorded_events` 中明确列出。
- 15 格中，三种受监测 Torch 抽样函数的实际调用均使用显式 generator；全局 Torch
  调用数为零。全局源的前后状态记录通过定向测试验证，不把不存在的实跑调用说成已覆盖。
- 30 次原版运行的 RRT* 回退均为零；未验证 C++ 规划随机性及回退路径，也不保证跨硬件／依赖逐位一致。
- BinFill medium 原 ep0 的受阻记录保留在冻结用例表，并在本轮重试对照中重新验证。
  本轮 15 格没有再更换 episode，没有放宽容差或跳过失败。
- 全量轻量测试已有的 4 个失败已在固定 `94449db` 复核：
  `test_unknown_env_returns_single_goal_when_equal`、`test_swingxtimes_multiple`、
  `test_step_error_returns_status_error`、`test_scripts_use_status_check_not_bare_try_except`。
  基线对应两个测试文件为 27 passed / 4 failed，1.02 秒，退出码 1；
  [baseline_test_results.txt](baseline_test_results.txt) 保存原输出，未修改范围外行为。
- 本轮先修正旧关键帧工具缺少事件映射、reset 原图和 worker 内类配置检查的问题，
  再发现并补齐随机调用前状态，所有中间产物均保留。首次离线反例测试因仓库内临时
  目录父级不存在而报 fixture 错误，创建父目录后 4 项全过；不是数据对拍差异。

## 测试结果

最终执行 `uv run --no-sync python -m pytest tests/lightweight/ -q --durations=5
--basetemp artifacts/test-tmp/action-freeze-final`：**232 passed / 4 failed，176.26 秒，退出码 1**，
在五分钟预算内。四个失败与固定基线逐项相同，不将全量套件称为全绿；原输出见
[final_test_results.txt](final_test_results.txt)，结构化命令和结果见
[tests_status.json](tests_status.json)。本轮对象／方向／交换反例、完整随机状态、字段消费
检查、最终图片绑定及交付证据检查均通过。

日志的入库文本副本只清理行末空白和末尾空行，以通过 Git 文本检查；完整原始日志保留在
`artifacts/logs/`，原始文件散列另记在 tests_status 中，未修改失败内容或结论。

独立交付离线检查 4 项通过，0.06 秒；覆盖完整矩阵、合并与连续指纹、重试／16 任务、
全部目视记录和篡改报告反例。规范日志文本副本后再次复验最终轻量包：**42 passed，0.36 秒，退出码 0**。

## 复现入口

从仓库根目录运行，重新生成须换一个未使用的运行编号。长任务用 detached tmux，
`PYTHONUNBUFFERED=1`、`pipefail`、`tee` 与 `EXIT_CODE=` 保存实际退出状态。

复用本仓库的锁定环境和 `artifacts/native-baseline` detached worktree；该 worktree 的
HEAD 必须为上述完整基线 SHA。不存在时先用
`git worktree add --detach artifacts/native-baseline 94449db0a068a6b454b55a13ebd48f0394d89cc8`
建立。下面的编号需换成未使用的值；本轮正式命令没有用 `--cell`、`--path` 或 `--no-steps`
缩减矩阵。

```bash
command -v uv
mkdir -p artifacts/logs
PARITY_RUN_ID=20260909-actions-reproduce
tmux new-session -d -s "$PARITY_RUN_ID" \
  "set -o pipefail; { PYTHONUNBUFFERED=1 uv run --no-sync python -m tests._shared.parity_runner --cases docs/validation/newtask-v2/cases.json --run-id $PARITY_RUN_ID && PYTHONUNBUFFERED=1 uv run --no-sync python -m tests._shared.action_freeze_campaign --run-id $PARITY_RUN_ID; } 2>&1 | tee artifacts/logs/$PARITY_RUN_ID.log; code=\$?; echo EXIT_CODE=\$code | tee -a artifacts/logs/$PARITY_RUN_ID.log; exit \$code"
```

`parity_runner` 逐格先校准 A1/A2，无规划回退且逐位一致才继续 B/C。
`action_freeze_campaign` 按完整打包、对象动作核验、15 格合并、三路连续 worker、
重试与 16 任务回归、全部关键帧出图依次执行。出图完成后还必须逐图检查并执行
`parity_review finalize`，不能把自动出图当作目视通过。

逐格 `parity_review collect --run-id <编号> --cell <格名>` 会准备原尺寸画板；实际查看后
用 `mark --manifest <manifest.json> --boards <已查看编号列表> --note <目视结论>` 登记。
全部 15 格完成后，用 `finalize --index <最终 keyframe_index.json> --review-root <本轮目视目录>
--output <visual_inspection.json>` 核验全集与图片散列。新一轮复现必须重新查看，不能照抄
本轮或其他历史运行的目视标记。

无需 artifacts 或 GPU 的离线检查：

```bash
command -v uv
mkdir -p artifacts/test-tmp
uv run --no-sync python -m pytest \
  tests/lightweight/test_action_freeze_delivery.py \
  tests/lightweight/test_native_sampling_evidence.py -q \
  --basetemp artifacts/test-tmp/action-freeze-offline
```

[bundle_manifest.json](bundle_manifest.json) 绑定所有轻量数据文件散列。HDF5、视频、
原始逐步证据、PNG 和完整日志留在本仓库 `artifacts/`，本目录只提交轻量证据。
