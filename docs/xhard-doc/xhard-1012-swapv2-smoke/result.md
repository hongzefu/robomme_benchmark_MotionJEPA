# 阶段 D：按钮包络读取失败，停止后续生成

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
