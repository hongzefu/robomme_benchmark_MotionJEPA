# BinFill 初始预填孔漏洞与实际入孔资格修复

本报告记录一次**已拒绝候选**暴露出的初始预填孔问题，以及几何认证和任务判定的修复。不能据此推断旧运行中完成认证的 84 条记录有问题：暂停前的只读检查覆盖了 22 个不同的、已完成第二次运行的 BinFill spec，未发现初始孔空腔占据；这项检查也不等于重新认证全部 84 条记录。

## 发现与可复核证据

问题发生在旧双卡运行的 `BinFill/hard/0001`、`candidate_index=3`、`seed=2000000017`。

- [拒绝记录](../../generated/robomme-icl/validation24-dualgpu/certification/BinFill/hard/0001/candidate_0003/rejected.json)：查看 `spec_hash`、`error`、`seed`。
- [冻结的名额和配置](../../generated/robomme-icl/validation24-dualgpu/prepare_state.json)：从 `slots` 选择 `slot_id="BinFill/hard/0001"`，使用 `candidate_for_slot(slot, 3)` 重建。
- [原正式运行日志](formal-dualgpu-v2/certification96.log)：检索该 slot 和 candidate。原运行优雅停止后记录 `EXIT_CODE=130`，未发布完整 96 条 suite。

重建的 spec 与拒绝记录中的哈希完全相同：

```text
965e8d490948b7beab42b234246cf86645a41e1c3addfd4ed53cd810dce03123
```

该记录的目标为 `target_counts={blue:3, green:0, red:2}`，`target_ids=[cube_1,cube_2,cube_3,cube_4,cube_5]`。其中蓝色 `cube_2` 的 `reveal_steps_by_id.cube_2=0`，属于开始时可见的目标方块。

| 几何量 | 实际值，单位 m |
| --- | --- |
| board 世界中心 | `(-0.020988621543345343, 0.030153228951293076, 0.025)` |
| cube_2 世界中心 | `(-0.014861297974828568, 0.03653951844632909, 0.020)` |
| cube_2 在 board 局部坐标中的 XY 中心 | `(0.007430499739629795, 0.0048079581161934075)` |
| cube_2 在 board 局部 X、Y 轴上的半投影 | 两轴均为 `0.026059294195580982` |
| 孔半宽 | `0.040` |
| 方块顶部／板顶部高度 | `0.040`／`0.050` |

两轴均满足 `abs(local_center)+projected_half_size < hole_half_size`，方块顶部也低于板顶部。因此，方块初始就完整处于孔内，而不是仅中心靠近孔口。

拒绝记录显示，在第 79 个控制步、机械手指与 board 碰撞时，`inserted_ids` 已有 `cube_2`，`color_counts` 已有 `blue:1`。这与初始预填被自动计数吻合。该候选本身已因真实碰撞拒绝，没有发布为认证环境。

## 已完成记录的只读核查边界

暂停前，读取旧输出目录 `certification/BinFill/*/*/candidate_*/repeat_1_infra_*.h5` 中 `complete=True` 的 HDF5，仅访问 `setup/episode_spec` 和 `setup/spec_hash`，按 spec 哈希去重。使用 board 的实际位姿、孔尺寸与方块真实 OBB，检查原始初始位姿是否与三维孔空腔有正体积重叠。

该次诊断的标准输出为：

```json
{
  "distinct_complete_repeat1_BinFill_records": 22,
  "initial_hole_occupancy": [],
  "read_skips": []
}
```

这里的 22 是**该次读取时的快照数量**，不是对随后收尾完成数量的重新统计。读取没有执行仿真，也没有改写 HDF5。

旧 oracle 没有明确的初始预填拒绝条件。预填目标被自动计数并停车后，后续抓取可能失败；非目标预填可能造成超额计数。这些都是依赖后续执行的间接拒绝，不能替代初始场景和判定器自身的正确性保证。

## 修复后的两个独立检查

几何入口 [validate_spec_geometry](../../../src/robomme_icl/geometry/collision.py) 增加 BinFill 初始检查，共用 `actor_occupies_binfill_hole` 定义孔空腔。

- 初始认证使用 `projected=True`：任意方块的真实形状与孔开口平面投影发生正面积重叠，就拒绝该候选；包括孔内、孔上方和部分覆盖孔口的方块。这样也阻止“初始悬在孔上方，靠重力零操作落入”。
- 检查包含动态方块的预定出现位置。动态开关不能绕过初始场景有效性。
- 使用投影凸多边形的分离轴检查，阈值为 `1e-10`；不把孔柱的高度粗略设成某个大常数。
- 孔空腔是语义区域，不是实际障碍。其检查结果不会混入 `min_clearance` 的物理碰撞距离，也不会约束正常搬运途中经过孔上方。

[TaskEvaluator._update_BinFill](../../../src/robomme_icl/tasks/evaluator.py) 只新增一份 `eligible_insert_ids` 资格状态，继续沿用完整形状入孔、释放和连续落稳要求。

| 观测事件 | 资格与计数变化 |
| --- | --- |
| reset 后首次观察到方块已在孔内 | 不取得资格，不自动计数 |
| 活动方块完整处于三维孔空腔外 | 取得后续入孔资格 |
| 已取得资格，随后完整进入孔并释放、连续落稳 | 仅计数一次，并记录到 `inserted_ids` |
| 初始孔内方块被垂直取出，再重新投入 | 取出时取得资格，重新入孔落稳后可计数 |
| 未计数方块进入停车状态 | 清除资格及稳定计数；停车位不能提供孔外证据 |
| 停车方块直接显现在孔内 | 没有资格，不计数 |
| 停车方块先显现在孔外，再正常投入 | 重新取得资格，正常计数 |
| 已计数方块被移到停车位 | 保留累计结果，不重复计数 |

不要求新增抓取历史，保持原任务“实际放入规定数量”的语义。环境 [ICLBaseEnv.snapshot](../../../src/robomme_icl/envs/base.py) 只新增 `parked_ids=sorted(self._parked)` 字段，为判定器提供明确的活动／停车状态。`reset()` 清空新增资格状态。

## 验证结果与当前状态

本次定向命令为：

```bash
command -v uv
UV_CACHE_DIR="$PWD/.cache/uv" uv run --no-sync python -m pytest \
  tests/robomme_icl/test_geometry.py \
  tests/robomme_icl/test_tasks.py \
  tests/robomme_icl/test_env_contract.py -q
git diff --check
```

结果为 **56 passed，6.50 s，退出码 0**；两条 warning 来自已安装依赖的弃用提示。`git diff --check` 通过。新增回归覆盖初始预填、高处落孔、部分孔投影、垂直取出再放回、无抓取历史的正常进入、停车后显现、动态孔外显现后投入和 reset 清资格。

根代理随后完成以下验证：

| 验证 | 结果与证据 |
| --- | --- |
| 完整新版测试目录 | `uv run --no-sync python -m pytest tests/robomme_icl/ -q`：`114 passed, 4 skipped`，`36.14 s`；结果由根代理同轮执行回传 |
| 新初始几何认证 | [geometry_preflight-v4.json](geometry_preflight-v4.json)：`expected_slots=examined_slots=passed_slots=96`，`elapsed_seconds=29.371893987059593`；明确标注 `coverage=compound_geometry_only` |
| 四任务真实双进程 smoke | [smoke-v3.log](smoke-v3.log) 与 [已发布小样本 suite](../../generated/robomme-icl/smoke-v3/suite.json)：四任务均通过独立进程逐位复现，共 `4/4` |

96 条几何通过不等于 96 条真实物理认证已完成。四任务 smoke 证明这次修复后的核心运行链路通过；旧 84 条完成记录继续保留为旧源码证据，不能仅因新源码修复就把它们改称为新版本认证结果。
