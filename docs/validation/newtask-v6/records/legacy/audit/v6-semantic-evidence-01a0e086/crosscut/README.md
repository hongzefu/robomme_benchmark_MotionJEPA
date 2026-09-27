# 横切语义与可视化核验

审查锚点 `AUDIT_BASE=0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8`。源码仅使用固定快照，后续主仓变化不属于本报告。所有HDF5为既有产物，只读分析，没有新增reset或轨迹，没有修改环境源码。

## 覆盖与来源

权威身份来自主仓 `artifacts/newtask-v6/s4-launch/verification/final-delivery.json::successes`，覆盖16环境、55格、165条正式交付。逐HDF5读取全部 `info/is_subgoal_boundary` 边界，保留演示标记和四个简单／坐标子目标字段，结果为 `all165-boundary-cache-check.json`。筛选条件是简单子目标相同、两份坐标文本不同且均含坐标占位。

全量扫描退出0，165条中75条存在上述字段差异。**75条字段差异不等于75条错误**：在线判定可提前切换，遮挡与可见质心变化也会造成差异。除ButtonUnmaskSwap之外，观察到的边界坐标差最大15.23像素，未据此判定指错对象。VideoUnmaskSwap代理补查hard三条无差异，新档五处差异仅1～5.4像素，未确认错误对象。

## 强反例：ButtonUnmaskSwap的在线缓存

`bus-first-pick-cache.json`覆盖四新档12条首抓：离线坐标与当前动作点距离2～5像素；其中10条在线坐标与当前动作点相距28.86～64.28像素，另外两条最终位置恰与缓存相同。

代表xhard1/episode3：第175帧在线文本首次成为 `pick up the container at <126, 118> that hides the blue cube`，第268帧仍保留该坐标；同帧离线坐标为 `<135, 179>`，动作点为 `[132, 182]`。已目视相邻目录 `../swap_button/ep3_timestep_268.png`，旧坐标落在另一只容器，当前动作点与离线坐标位于右侧目标容器。

固定源码根因：`utils/segmentation_utils.py::process_segmentation`只在子目标文本变化时刷新坐标；`RecordWrapper::step`把online已有文本与点传回该函数。交换期间语言文本相同，因此交换前缓存未更新。该项是实际交付中的错误视觉指示，不仅是字段格式不同。

## 其他横切结论

- VideoRepick的一个替代表述把执行重复次数写成历史演示次数，`utils/task_goal.py::get_language_goal`使用“the same cube that was previously picked up twice／N times”；环境演示仅一次抓放，执行才重复N次。全部替代表述进入视频字幕、HDF5任务文本与在线观测。Repick代理的21条HDF5复核显示18条N>1携带该歧义表述，详见同级 `../repick/h5-task-segments.json`。这是语言契约问题，不等于物理执行次数错误。
- 四Unmask环境的VQA容器抓取候选 `available` 只包括 `spawned_bins`，不包括可见 `distractor_bins`。`OraclePlannerDemonstrationWrapper::_apply_position_target`交给`choice_action_mapping::select_target_with_pixel`在候选集合内无距离门槛选最近点。因此指向外环干扰物会吸附为内环对象，单列为**选择式评估风险**，不冒称专家视频抓错。
- 网站VPB/VPO把携带交换标志的`static`也译为“静止”；实际是机械臂等待、平台运动。属于展示说明不完整，不能等同答案错误。
- MoveCube VQA只有hook的初步疑点已排除：后续选项还有push等动作。网站按HDF5真实边界保留连续同名子目标，未将NO RECORD伪造成可见动作。

## 可复跑命令

在主仓根目录，先核对 `command -v uv`、`uv.lock`和`pyproject.toml`。下列命令不导入仓库源码、不启动仿真；全量扫描只读取现有HDF5。已有输出拒绝覆盖。

```bash
UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/cache/uv uv run --no-sync python artifacts/audit/v6-semantic-evidence-01a0e086/crosscut/check_boundaries.py --manifest artifacts/newtask-v6/s4-launch/verification/final-delivery.json --compare artifacts/audit/v6-semantic-evidence-01a0e086/crosscut/all165-boundary-cache-check.json
```

固化脚本后以同命令追加 `--limit 1` 做一条自检，对照原始扫描的完整记录，不重复扫描165条。完整扫描原结果来自会话内同等逻辑的只读内联程序。

固化后自检退出0、耗时0.238秒：`BOUNDARY_SCAN=PASS episodes=1 mismatched_episodes=0 audit_base=0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8`。该PASS只证明选中一条的重读结果与原证据相同，不表示165条语义全部正确。

## 未覆盖与验证边界

- 全量扫描覆盖子目标边界，未逐帧判定每一个像素指示，也未用字段不等直接给错误数。
- 165条扫描不覆盖候选未交付局、失败局和原三档；其他代理的原档复核单独注明。
- 没有新运行选择式策略，VQA干扰物限制是源码路径证据。
- 没有新增仿真、碰撞探针、reset或轨迹；不据此保证所有物理行为和所有颜色语义正确。
- 录像拼接、任务文本输出与网站子目标提取作了静态检查，未重跑浏览器完整交互测试。
- 一次中间排名输出因同距离元组比较到字典而退出1；改为按距离显式排序后退出0；165条原扫描与其结果未受影响。
