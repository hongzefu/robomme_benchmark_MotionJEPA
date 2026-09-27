# 独立复核记录：crosscut-language-05（SwingXtimes 主目标漏 put-down）

AUDIT_BASE = 82e3d922b78d48ec1e825b168cccc0e1b8c690c1（只用 `git show` 读取，未读工作树/其它 ref）

## 源码锚点复核
- `src/robomme/robomme_env/utils/task_goal.py::get_language_goal`（SwingXtimes 分支，repeats>1）：
  `task_goal[0]` 模板 = "... repeating this back-and-forth motion {word} times, finally press the button to stop"（**无 put-down**）；
  `task_goal[1]` 模板 = "... repeating this right-to-left swing motion {word} times, then put down the cube and press the button to stop"（**含 put-down**）。
  该分支不含任何 `difficulty` 判断，repeats>1 时两条模板对全部难度档一视同仁。
- `src/robomme/robomme_env/SwingXtimes.py::_load_scene`：task chain 无条件追加
  `{"name": "put the {color} cube on the table", func: is_obj_dropped}` 然后
  `{"name": "press the button", func: is_button_pressed}`（即 put-down 恒在 press button 之前），
  同样不含 `difficulty` 分支——`difficulty` 只影响 `num_repeats` 的采样范围（number_range 配置），不影响模板结构或链条顺序。
- `0925-newtask-release-v6-plan.md` 第 66/193/270 行只提到 SwingXtimes 各档「轮数/干扰块」数值梯度，未提及语言模板结构变化，因此该行为在计划中就是"应保持不变"的部分——不存在"新档未遵计划擅自改变行为"的问题。

## 数据独立复核（全量，不止 finding 给的单点）
脚本：`subgoal_chains_full.py`（内联于本次 bash 调用，产物见 `subgoal_chains_full.json`），对
**native 全部 9 个 episode**（`artifacts/newtask-v6/v1/base/B/SwingXtimes_episode_*`）与
**新 tier 全部 12 个 episode**（xhard1-4，来自 `new-tier-index.json`）逐条重新解析
`setup/task_goal` 与 `info/simple_subgoal` + `info/is_subgoal_boundary` 构造的 subgoal chain，
统计结果见 `summary.json`：

| 集合 | episode 数 | goal0 含 put-down | chain 中 put-down 先于 press button |
|---|---|---|---|
| native (easy/medium/hard) | 9 | 1/9（仅 ep2，repeats=1 走 else 分支，模板本身含 put-down，non-repeats 情形不在 finding 范围内） | 9/9 |
| new tier (xhard1-4) | 12 | 0/12 | 12/12 |

与 finding 给出的"8/9 native episodes (all repeats>1)"完全吻合（9 个 native 里唯一
goal0 含 put-down 的 ep2 正是 repeats=1 的情形，finding 的分母已排除它，故 8/9 严格对应）；
12/12 新档同样零例外。finding 给出的具体锚点
（`SwingXtimes_ep0_seed6300000.h5` t=1089 "put the red cube on the table"、t=1129
"press the button"）已在本次独立重跑中逐位复现（见下方 subgoal_chain 片段）。

独立新增证据点（finding 未引用）：
- native `SwingXtimes_ep0_seed3000.h5`（easy, repeats=2）：t=344 put-down，t=379 press button，
  goal0 = "pick up the red cube, move it to the top of the right-side target, then move it to
  the top of the left-side target, repeating this back-and-forth motion twice, finally press
  the button to stop"（无 put-down）。
- new tier `xhard1 SwingXtimes_ep0_seed8300000.h5`：goal0 同样无 put-down（"...repeating this
  back-and-forth motion four times, finally press the button to stop"），mp4 文件名
  （见 `new-tier-index.json`）与 chain 顺序一致确认。

## 是否重复已排除项
不属于 EXCLUDED 列表 F1-F7/D1-D7 中任何一条，也不是 left/right 措辞问题，也不是纯网站文案问题。

## 类别判定复核
`native_same` 正确：native 与新 tier（xhard1-4）在代码路径、模板结构、chain 顺序上完全一致，
且 `difficulty` 变量不参与该分支的模板选择，仅参与 `num_repeats` 数值采样；这不是"新档相对
native 引入的行为差异"，而是 SwingXtimes repeats>1 模板本身自带的、跨全部难度档一致存在的
语言-视频不一致（`task_goal[0]` 与实际 chain/`task_goal[1]` 不符）。

## 结论
CONFIRMED。证据独立可复现，无需新增仿真。
