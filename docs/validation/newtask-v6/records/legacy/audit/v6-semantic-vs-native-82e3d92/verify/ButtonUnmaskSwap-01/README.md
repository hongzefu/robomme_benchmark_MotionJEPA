# Verification of ButtonUnmaskSwap-01 (AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

独立复现，脚本: analyze_seg.py (本目录未拷贝原脚本，逻辑自写)。

## 源码核对
- `git show 82e3d922...:src/robomme/robomme_env/ButtonUnmaskSwap.py`
  第806-811行: `if self._is_newvalue: tasks[1]["solve"] = lambda env, planner: self._solve_press_then_wait_swaps(env, planner, self.button_left)`，
  中文注释明确说明动机："原解法会在容器还在交换时就去抓（实测 2/2 失败）"。
- `_solve_press_then_wait_swaps`（第945-953行）：先 `solve_button` 按下，再
  `solve_hold_obj_absTimestep(absTimestep=self.swap_schedule[-1][3])` 原地等到最后一段交换结束。
- `is_newvalue_difficulty`（difficulty.py）严格等于 {xhard1,xhard2,xhard3,xhard4}，原三档 (easy/medium/hard)
  从不满足，故该等待机制严格限定新档 —— 支持 category=new_tier_only。
- `0925-newtask-release-v6-plan.md` §四.4 (ButtonUnmaskSwap 段) 只提 "BUS 评估步 ≤ 约 820"，未提及任何等待/静止段。

## 数据独立复现（h5py 直接读取 info/simple_subgoal + obs/eef_state）
| episode | tier | press-second-button 段长 | 段内末尾静止步数(位移<1e-4) |
|---|---|---|---|
| native ep7 | hard | 93 | 0 |
| native ep0 | easy | 91 | 0 |
| native ep2 | medium | 95 | 0 |
| xhard2 ep0 | xhard2 | 111 | 17 |
| xhard4 ep0 | xhard4 | 220 | 123 |

与 finding 原始数字（91-99 / 0-1 步；xhard2 18；xhard4 124）一致（±1 步差异来自静止判定阈值/边界定义，
不改变结论）。eef z 轨迹显示 xhard4 ep0 在 t≈175 触底(0.0244m，物理按下)后立即回抬到 z≈0.148m 并保持不动，
直到 t=332（段末），下一子目标"pick up ... blue cube"从 t=333 开始；这与视频证据一致。

task_goal 字符串核对（xhard4 ep0）：
"first press both buttons on the table, then pick up the container hiding the blue cube, ..."
— 未提及任何等待/暂停，印证 what_language_says。

## 排除清单核对
不与 F1-F6 / VPB / D1-D7 / 左右手性 / 纯网站文案类问题重叠：本条是 ButtonUnmaskSwap 的等待时长与
标签滞留问题，F3（label vs VQA binding）和 F4（swap 后 grounded_subgoal 坐标过期）都是不同性质的问题
（前者是按钮身份映射，后者是坐标不更新），不构成重复。

## 结论
CONFIRMED。category=new_tier_only 正确（机制严格由 `self._is_newvalue` 门控，原三档代码路径完全不可能
产生此行为）。不需要新跑模拟——现有交付数据（native 9 集 + xhard1-4 各3集）已经足以证实该发现。
