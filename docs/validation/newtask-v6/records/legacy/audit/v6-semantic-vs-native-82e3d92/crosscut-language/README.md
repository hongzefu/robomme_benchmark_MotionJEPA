# 跨环境语言 / 子目标模板审查（crosscut-language）

- `AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1`；源码只经 `git show AUDIT_BASE:<path>` 读取；收官复核 HEAD 仍为该 sha、`git status --porcelain` 为空。
- 纯审计：未导入 robomme / sapien / gymnasium，未运行 scripts/ 或 tests/；本目录外未写任何文件。
- 数据范围：新档交付 165 条（`new-tier-index.json`，与 `v6-01/*/specs.jsonl` 中 550 条规格逐条按 (task, difficulty, episode, seed) 对上，缺失 0）+ 原三档 144 条（`newtask-v6/v1/base/B`）。

## 做了什么

| 步骤 | 脚本 | 产物 | 判定行 |
|---|---|---|---|
| 抽取 309 条 HDF5 的 `setup/task_goal`、`available_multi_choices`、逐边界 `simple/grounded_subgoal`、`choice_action` | `extract.py` | `records.json`、`goals_all.txt`、`subgoal_vocab.txt` | `EXTRACT=PASS records=309 new=165 native=144` |
| 语言目标 ↔ 子目标链 ↔ 规格参数 ↔ 计划第三节取值表三方核对 | `check.py` | `checks.json` | 仅 3 类失败，见下 |
| mp4 文件名中的档名与语言目标 ↔ HDF5 | `mp4_goal_check.py` | — | `MP4_GOAL_MATCH=PASS mp4=353 mismatches=0` |
| BinFill / PickXtimes / SwingXtimes：子目标颜色词 ↔ 抓取点像素色相 | `pick_color.py` | `pick_color.json` | 新档 223/223、原三档 63/63 一致 |
| Unmask 四环境：子目标「hides the X cube」↔ 容器抬起后露出方块颜色 | `unmask_reveal.py` | `unmask_reveal.json` | 新档 132/132、原三档 51/51 一致 |
| VPB / VPO：语言目标颜色 ↔ 执行段实际抓取方块颜色 | `vp_color.py` | `vp_color.json` | 新档 24/24、原三档 18/18 一致 |
| grounded 子目标缺坐标统计 | `nocoord.py` | `nocoord.json` | 执行段 新档 11/1011（1.09%）、原三档 2/407（0.49%） |
| VR 演示交换运动窗口 ↔ static 子目标边界 | `vr_swaps.py` | `vr_swaps_xhard4.json`、`vr_swaps_native.json` | 见发现 L3 |
| VPB 第 3 句备选语言的指向唯一性 | `vpb_alt_ambiguity.py` | `vpb_alt_ambiguity.json` | `VPB_ALT3_AMBIGUOUS after=5 before=2 total=12` |
| 模板变体 / 分档分支 / 子目标词表汇总 | `build_templates.py` | `templates.json` | `TEMPLATES_JSON=WRITTEN envs=16` |

自动核对全部通过的项目（新档与原三档）：BinFill 各色数量与子目标抓取次数、序数连续、单复数；PickXtimes / SwingXtimes / VideoRepick 次数词 = 子目标次数 = 规格 `num_repeats`，且落在计划区间；Unmask 四环境语言颜色序列 = 子目标颜色序列 = 规格 `n_picks`，swap 次数落在计划区间；PickHighlight 抓取数 / 总块数 = 计划 4/7、5/8、6/9、7/10；StopCube 两句序数一致且 = 规格 `stop_time`；VPO 序数 = `which_in_subset`，答案 target = 答案方块第 n 次访问的 target，总放台 5/6/7/8；VPB 放台次数 3/4/5/6；PatternLock 节点数 / RouteStick 段数落在计划区间；PickXtimes / SwingXtimes 干扰块 1/2/3/3 且为 yellow/cyan/magenta。

## 发现（详见结构化输出）

- **L1 SwingXtimes xhard4 子目标序数写成「11th」**（新档独有，低）：`SwingXtimes.py::_load_scene` 本地序数表只到 tenth，超出写 `f"{i+1}th"`；xhard4 ep0（t=1000/1044）、ep6（t=895/934）两局 22 个往返子目标里出现「for the 11th time」，而语言目标写「eleven times」、其余序数全是单词。`utils/subgoal_language.py` 的 V4 E2 已把序数表扩到 twentieth，但本环境未接入。
- **L2 VPB 第 3 句备选语言「where it was previously placed after the button was pressed」在新档不唯一**（新档独有，低～中）：新档额外放台（`extra_place_after`）的 owner 恰为答案方块时，按钮之后该方块放到两个 target 上；交付 12 局中 5 局（xhard1 ep0/6、xhard2 ep0/3/6）为 after 题且命中；原三档 `additional_place=False`，按钮后只放一个 target 再放桌面。主句「right after」、ALT「immediately after」「first placed after」仍唯一。帧证据 `frames/vpb_xhard1_ep0_*`。before 侧的同类情况（xhard3 ep3/6）属已排除的 VPB 绑定问题，只记已见。
- **L3 VideoRepick xhard4 ep3 演示段 static 子目标边界比交换次数少 1**（新档独有，低）：规格 `n_swaps=12`，rng_trace 记录 12 个交换窗口，像素运动窗口 12 个，但交换阶段 static 边界只有 11 个（原三档 6 局与新档其余 11 局均为 n_swaps+1）。
- **L4 PickHighlight 新档子目标去掉颜色后缀、且按钮前抓块才真正判失败**（新档独有，低，有 V4 依据但 V6 计划未写）：`subgoal_color_suffix=omit` 使序数「first/second highlighted cube」失去颜色锚；`button_failure_func` 新档是 lambda，原三档是构造时求值的常量（从不触发）。
- **L5 SwingXtimes 主语言目标漏写「放下方块」步骤**（与原三档相同，低）：repeats>1 的第 1 句只写 finally press the button，任务链与判据要求先「put the X cube on the table」；21 局中 20 局命中。
- **L6 grounded 子目标在目标被机械臂遮挡时缺坐标**（与原三档相同，低）：新档执行段 11 处、原三档 2 处，比例无显著差别；`choice_action.point` 仍在。帧证据 `frames/nocoord_*`。

## 已见但属排除清单（不重复报告）

F1、F2、F3（未复查）、F4（未复查）、VPB last-placed-before 绑定（xhard3 ep3/6，本目录 `vpb_alt_ambiguity.json` 中 before 侧 2 局即此）、D2 左右均为机器人坐标系、D5 站点「静止」标签（VR/VPB/VPO/VU 交换段子目标 = static）。

## 未覆盖

判据阈值只查了与语言直接相关的部分（SwingXtimes `max_swings=2*num_repeats`、StopCube 停止窗、PickHighlight 按钮前抓取失败）；BinFill 实际入箱数、PickHighlight 被抓方块是否确为高亮块、MoveCube / InsertPeg 视觉细节未逐帧核对（由分环境审查覆盖）。
