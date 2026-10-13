# 阶段 D：方案 A 与四卡 smoke 已通过

最新结论：W3 按根位姿与真实关节帧推导按帽，D1b 十八项全部通过；四卡 smoke 三条任务成功、一条按预定 graph 判据正常拒绝，四个身份全部符合计划。旧目录四百二十六文件完整哈希再次通过。下面保留首次失败及诊断的历史证据，最新实测见末节。

最小 GPU 复位通过，但完整 GPU 契约未通过：ButtonUnmaskSwap seed 7700 在建场阶段报「按钮包络读取失败 bystander_0：ValueError: 按帽水平投影超出底座」。按计划闸门停止，四卡 smoke 和全量均未启动；不把这次读取失败作为正常碰撞剔除。

## 用户授权与版本

用户本轮原话：「根据最新的计划修正后的内容 继续」；执行中追加：「本次不用再审核了，继续」。按该追加指令不再派独立审查，继续运行已批准 GPU 验证。计划自身明确 GPU 契约失败时「停，报证据」，本结果记录的是该运行失败闸门，不是新增审查要求。

实际启动提交为 `6c7254cc4d9464cf022fe1045f66f67c2002e106`（2.96.1），两次 GPU 调用前工作区干净，结束后 HEAD 仍相同。完整命令、输入、运行器哈希和资源约束见 [启动档案](launch.md)。本机 sled-vail GPU0，起跑前 1286 MiB / 46068 MiB、利用率零；没有更换卡或后端，没有改依赖、阈值或包络尺寸，没有重试。

## 实测判定及未执行内容

- `GPU_MIN_RESET=PASS tests=1 seconds=7.47 exit=0`：VideoUnmaskSwap 5700，单任务复位及 G/预写配对验证。
- `GPU_CONTRACT=FAIL passed=1 failed=1 remaining=15 seconds=8.39 exit=1`：原十七项 GPU 验证，仅第一项通过；第二项在 `gym.make` 建场时失败，`-x` 停止，后续十五项未执行。
- `XHARD_FATAL_CATCH=NOT_RUN`：三任务运行期故障送达未执行。
- `SWAP_V2_SMOKE=NOT_RUN cards=4`：5700、9300、10500、11200 四卡生成未执行。
- `XHARD_FULL_DERIVE=NOT_RUN expected=180`：全量未报批、未启动。

失败节点为 `src/robomme_xhard/tests/test_swap_collision_gpu.py::test_reset_certifies_all_pairs[ButtonUnmaskSwap-ButtonUnmaskSwapXHard-7700-spawned_bins-bin_]`。调用链为官方父类构造 → `BaseEnv.reset(reconfigure=True)` → `BaseEnv._reconfigure` → 子类 `_load_scene` → `certify_swap_plan` → `bystander_states_of` → `button_envelope_state`。失败发生在按帽和底座水平投影包含性检查，尚未进入可行图计算或轨迹交换，因此不能据此判断配对算法的真实轨迹成功率。

完整原日志为 `artifacts/logs/xh-swapv2-d1-min-1012.log`、`artifacts/logs/xh-swapv2-d1-1012.log`，文档记录只清理行尾空白，保存在 `records/gpu_min.txt`、`records/gpu_contract.txt`。D1 日志记录 `SOURCE_HEAD=6c7254cc4d9464cf022fe1045f66f67c2002e106`、启动时间 `2026-10-12T21:04:32-04:00` 和 `EXIT_CODE=1`。

## 只读定位：前置探针没有覆盖相同读取时点

已确认的代码事实：

1. 生产认证位于 `ButtonUnmaskSwapXHard::_load_scene` 的父类建场返回后。`ManiSkill BaseEnv::_reconfigure` 的顺序为 `_load_scene(options)`，随后才执行 `scene._setup(enable_gpu=...)`。
2. 阶段零 `graph_scan.py` 只用记录器替换 xhard 认证，在 `gym.make` 和 `env.reset` 返回后才调用 `button_states` 读取按钮世界位姿。先前按钮预扫通过证明的是这个较晚时点，不证明生产认证时点已经可读。
3. 依赖 `ArticulationBuilder::_build_entities` 构造全部连杆后只将根 `entities[0].pose` 赋为 `initial_pose`；子连杆由关节结构连到根。本轮 `button_envelope_state` 直接消费底座、按帽各自的 `component.entity.pose`。

据此，较早认证时子连杆世界位姿尚未就绪是候选原因。现有失败日志没有 `bp/cp/blo/chi` 的数值，不能把候选写成动态验证过的根因。没有追加 reset、探针或代码修补。

候选下一步为同一 GPU0、同一 ButtonUnmaskSwap 7700 的单任务数值诊断，最多一次、五分钟以内、无 rollout：在原失败测试加入 `--showlocals` 以记录底座／按帽世界中心及边界，确认是否属于初始化时点差异。该诊断需要用户下一步授权；不自动重试。确认后再提出具体修法：优先保持当前认证钩子、接口、静态按钮包络口径和阈值，若必须调整钩子或时序则按重大口径变更停下修订完整计划。

## 会话及证据保留

本批实际启动会话只有 `xh-swapv2-d1-1012`，pytest 正常错误退出后会话自然结束；`xh-swapv2-smoke-1012` 没有创建。面板 shell PID 48517 为退出后的僵尸，不是运行中的 GPU worker；没有活跃的本轮 pytest。仅停止本轮日志监听 tail PID 50172，监听管道退出 143；这个监听退出码不与测试退出码混用。没有停止用户其他 tmux 会话、GPU 任务或服务。

旧根仍保持只读；阶段 D 后按原冻结清单逐文件 SHA256 复核，结果日志为 `artifacts/logs/xh-swapv2-old-root-after-d1-1012.log`，完成后在下节记录。不清理失败日志、已有原图、视频、H5 或工作树。

## 旧结果完整性复核完成

`OLD_RUN_INTACT=PASS files=426 mismatches=0`，全量 SHA256 复核退出零；文件数仍为四百二十六。另逐条对照字节数清单并检查目录与文件权限，`OLD_RUN_SIZE_MODE=PASS files=426 size_mismatches=0 writable=0`。完整复核日志归档到 `records/old_run_integrity.txt`。旧证据尤其六列视频没有覆盖、删除或新增文件。

## 用户授权的一次数值诊断

用户对限定问题选择原话：「允许这一次数值诊断（推荐）」。该授权只覆盖 GPU0、同一 ButtonUnmaskSwap 7700、五分钟内、无 rollout 的 `--showlocals` 诊断，不覆盖代码修补或继续批次。本轮未追加独立审查。

实际启动提交为 `dad0447160d939700d1cddfedc8b7a87d0f5e885`（2.96.2），工作区干净。GPU0 起跑前 1286 MiB / 46068 MiB、利用率 12%，符合环境 B 且未被占满。完整命令如下，外围使用 pipefail、tee 和 `EXIT_CODE=`；外层 280 秒上限：

```bash
CUDA_VISIBLE_DEVICES=0 UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1 timeout 280s uv run --no-sync python -m pytest 'src/robomme_xhard/tests/test_swap_collision_gpu.py::test_reset_certifies_all_pairs[ButtonUnmaskSwap-ButtonUnmaskSwapXHard-7700-spawned_bins-bin_]' -m gpu -q -rf -x --showlocals
```

仅执行一次，复现同一错误，pytest 为 `1 failed, 8 warnings in 3.84s`、`EXIT_CODE=1`。这是完成数值采集，不是修复通过：`BUTTON_DIAGNOSTIC=DONE attempts=1 reproduced=1 seconds=3.84 pytest_exit=1 read_xy_delta_mm=218.944809`。原日志 `artifacts/logs/xh-swapv2-button-diagnostic-1012.log`，完整记录 `records/button_diagnostic.txt`，结构化提取 `records/button_diagnostic_values.json`。

| 读取量 | 实测值，米 |
|---|---|
| 底座盒体中心 `bp` | `[-0.20180713, -0.08491591, 0.0075]` |
| 按帽圆柱中心 `cp` | `[0, 0, 0.009]` |
| 底座水平边界 | x 为 `[-0.23930713, -0.16430712]`，y 为 `[-0.12241591, -0.04741590]` |
| 按帽水平边界 | x、y 约为 `[-0.0225, 0.0225]` |
| 关节位移 `qpos` | `[0]` |
| 底座半尺寸、按帽半径／半长 | `[0.0375, 0.0375, 0.0075]`；`0.02250000089406967`／`0.008999999612569809` |

数值确认：生产建场读取时，底座已位于真实世界位置，按帽读数仍在原点附近，没有包含底座的世界平移。两组读数的水平中心差为 218.944809 mm；这是不一致的坐标读取，不能解释为实物真的偏离了约二十二厘米，也不能通过放宽 `1e-8` 包含性检查解决。结合前述 `_load_scene` 早于 `scene._setup`、构造器仅显式赋根位姿的代码事实，问题已定位到建场期子连杆位姿尚未完成同步的读取路径。

下一步候选是在 `swap_plan.py::button_envelope_state` 内，用已就绪的根世界位姿及真实关节父子变换、真实碰撞形状构造未按下包络，保持认证钩子、统一转换入口、几何保证与阈值不变；此修法没有实施或验证。若必须改变认证钩子或时序，仍按重大口径变化交用户。本轮授权到此完成，保持停工，不修代码、不重跑 GPU 契约、不启动 smoke 或全量。`DIAGNOSTIC_CODE_UNCHANGED=PASS`，运行前后源码、测试、生成器与依赖没有改动。

## 后续获批的方案 A 与四卡验证

用户后续原话：「参考最新的计划，继续进行。」据最新 2.96.5 计划实施 W3，只写规划模块与两测试文件；子提交 `b251f9c958c0ddba25d22481072faea39209fe9e` 合并为 `d19c873da43ac71fcd6787c0eb248882f9bf6e97`。主检出核心 440 项通过、原四项失败、二跳过，8.71 秒；按原节点基线 `CORE_SHORT=PASS new_failures=0`，pytest 实际退出 1。认证钩子、时序、包络与阈值不改。

实际 D1b 和 smoke 启动提交为 `e6e2d1e5d2ab6a428b271d92cd0e476480c59a68`（2.97.1），起跑与结束 HEAD 相同、源码未变；全程本机 GPU0。会话分别为 `xh-swapv2-d1b-1012`、`xh-swapv2-smoke-1012`，均已自然结束，监听尾进程按 `EXIT_CODE=` 结束自行退出。旧 D1 与诊断没有覆盖。

- `GPU_MIN_D1B=PASS tests=1 seconds=7.70 exit=0`：原失败 BUS 7700 复位现在通过。
- `GPU_CONTRACT=PASS tests=18 seconds=262.99 exit=0`。
- `BUTTON_POSE_LOADTIME=PASS buttons=3 max_dp_m=0 max_angle_rad=4.4408920985e-16`。
- `XHARD_FATAL_CATCH=PASS tasks=3 hang=0`。
- `SWAP_V2_SMOKE=PASS cards=4 task_success=3 graph_reject=1 infra=0 attempt0=1 generator_exit=1`。
- `SMOKE_H5=PASS files=3 labels=3 completion=3 rgb_contract=3`。
- `OLD_RUN_INTACT=PASS files=426 mismatches=0`，结束后完整 SHA256 退出零；另核对全部文件字节数一致。

| 官网编号 | 任务／seed | 任务成功 | 判定 | 帧数 | 墙钟秒 | 最长规划参与次数 |
|---|---|---|---|---|---|---|
| 2.3 | VideoUnmaskSwap 5700 | 1 | 成功 | 871 | 104.539 | 5、5、6、6 |
| 2.3 | VideoUnmaskSwap 9300 | 1 | 成功 | 890 | 81.466 | 6、5、5、6 |
| 2.4 | ButtonUnmaskSwap 10500 | 0 | reset 的 graph 阶段正常拒绝，未换 seed | 无 | 2.843 | 无 |
| 3.2 | VideoRepick 11200 | 1 | 成功 | 1367 | 52.282 | 10、10、10 |

四卡总墙钟 245.4 秒，单 worker 峰值 RSS 7176.0 MiB。生成器因一张正常拒绝卡退出 1；它本来就按有失败卡返回非零，不能把这个退出码篡改为零。四卡验收逐身份核对既定的成功与预期 graph 拒绝，缺项、重复、未知、infra 均为零，符合批准计划。

三个成功 H5 的 seed、xhard20 标签、帧数与末帧完成标志均命中；首帧 front_rgb 为 256×256×3 uint8。H5 大小分别为 580650224、593316616、911302600 字节，产物留在 artifacts，不进入 Git。主会话从三个成功视频各取一帧目视；5700 的较远搭档段中点 step 289、9300 step 189、11200 step 450，图像加载正常、对象显示且没有明显相互穿入。该三帧抽查不替代整段数学判据，机械臂与桌面仍在已声明盲区。

完整原日志和 `run_summary.json`、`episode_results.jsonl` 留在 artifacts；文档保存原 GPU 日志、去掉末尾整包 JSON 的 smoke 汇总文本、四行结构化判定、H5 核对和抽帧索引。删去整包 JSON 只发生在文档摘要，原日志与完整原账本不变。
