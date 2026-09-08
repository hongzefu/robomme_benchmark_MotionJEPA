# 原版行为对齐计划

基线：`76ae12bf1e71f79e1c3f608eede10ac7430b406f`。对照标准为该基线的 `src/robomme`。用户保留新版次数配额和位置分层；因此不要求原版随机 seed 与新版 seed 产生同一随机布局，但相同场景参数必须具有相同素材、subgoal 与显隐机制。

## 第一部分：实施目标和验收

旧版 ICL 的自身两次运行相同，只能证明自身复现，不能证明与原版一致。当前四个子类只选择独立判定器，原版的任务流程没有被继承，已存在可见差异。

把新版的参数化场景与原版任务机制相接：复用原版素材构建器、任务列表、每个任务的判定及 solve 函数、逐步事件；保留配置编译、独立注册 ID、套件和数据入口。必要时只把原版已有素材／任务列表代码提取为可调用方法，默认原版调用顺序、参数和语句保持不变，不用复制另一个实现来宣称一致。

首先以单任务、单局、单 worker 检查创建、reset、完整任务执行。随后按四任务三难度覆盖素材、subgoal、演示／执行边界、显隐窗口、交换起止、按钮终止和失败行为。检查真实 visual/collision shape 与材质，不以对象名字或截图相似替代。保留原始 RGB 和事件报告作目视证据；执行 `NO RECORD` 动作但按原版规则从交付演示中排除相应帧。

配置改变的次数和位置是允许差异；素材颜色规则、几何、事件触发方式、物理行为和 subgoal 不允许自行简化。旧套件不覆盖，修复后必须重新认证。未通过的项目必须明确列出，不能用最终 success 掩盖。

## 第二部分：代码、命令和记录

- 原版锚点：`BinFill._load_scene/_initialize_episode/step`、`RouteStick._load_scene/evaluate/step`、`VideoUnmaskSwap._load_scene/_refresh_swap_schedule/step`、`VideoRepick._initialize_episode/step`；`utils/object_generation.py`、`utils/statechange.py`、`utils/subgoal_evaluate_func.py`、`utils/subgoal_planner_func.py`。
- 新版改动集中于 `src/robomme_icl/envs/`、`legacy_bridge/`、`oracle/`，按真实素材校正 `suite/` 与 `geometry/`，并调整记录／回放以保存原版 subgoal 边界。新增定向行为对照测试；保留新版分布配置。
- 原版抽取方法前后用固定基线比较代码体；对照执行使用固定基线的原版方法，不只让两边调用同一新版适配器。
- 测试由 `command -v uv` 确认后使用 `uv run`；每轮定向验证控制在五分钟以内。真实生成先单任务单局 smoke，通过再增加覆盖；正式批量诊断使用登记的 detached tmux、仓库内日志和 `EXIT_CODE=`。
- 报告目录：`artifacts/reports/robomme-icl/native-parity/`；新生成产物：`artifacts/generated/robomme-icl/native-parity/`。不覆盖 `scripts-v1`，不修改或下载官方参考数据。
- 每阶段核对自身明确文件、`git diff --check`、测试结果，按中文版本提交并立即推送既有上游。最终记录提交、锁文件摘要、场景配置、seed、GPU、worker、命令、结果和未解决项。

## 初始反例

| 任务 | 原版机制 | 修复前新版差异 |
| --- | --- | --- |
| BinFill | 棕色孔板加黑色孔底视觉；原版投入判据后移到 `[10,10,0]` | 灰色无孔底板；独立落稳判据和停车位 |
| RouteStick | 九个灰白圆形标记、四个障碍、原版高亮和强制 reset 子目标 | 五个方形目标；没有完整高亮／隐藏帧流程；直接重置机器人 |
| VideoUnmaskSwap | 容器在绝对步 32 返回，64 开始交换；内容在交换期间移走，结束返回 | 新时间线、不同材质／几何、独立动画和判定 |
| VideoRepick | 演示抓放、可选静止及 swap 标志、强制 reset、执行抓放与按钮 | 简化演示，直接复位全部方块／机器人，独立抓放判定 |
