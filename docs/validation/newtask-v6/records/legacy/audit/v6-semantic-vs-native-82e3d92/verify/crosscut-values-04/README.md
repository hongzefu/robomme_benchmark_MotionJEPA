# crosscut-values-04 独立复核

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1（只读 git show）。

## 结论：CONFIRMED

独立直接读取 HDF5（不依赖 measured.json/scan_raw.json 的既有数字），用 `info/is_completed`
首次为真的 timestep 作完成边界、`info/is_video_demo` 计数演示帧，复算 exec_steps_to_completion：

- PickXtimes xhard2 ep0：n_steps=1390, n_demo=0, first_completed_t=1350 → exec_steps_to_completion=1350，
  与 measured.json 完全一致，且 >1300（`scripts/evaluation.py::max_steps=1300` 冻结值，
  `git show 82e3d922...:scripts/evaluation.py` 第85行 `max_steps=1300`）。
- PickHighlight xhard4 三个 episode（ep0/3/6）：first_completed_t 分别为 1241/1143/1125，
  均 < 1301，与 measured.json 一致，**没有一个超过 1301**。

## 与计划原文对照

`git show 82e3d922...:0925-newtask-release-v6-plan.md` 第 120 行（四、7 BinFill/PickXtimes/
SwingXtimes/PickHighlight 一节）原文：

> PickX xhard3/4、BinFill xhard3/4、PH xhard4 会超 1301 步（允许）。

- PickX xhard3/4、BinFill xhard3/4：measured.json 三个 episode 全部超过 1301 —— 与计划一致（未反驳）。
- **PH xhard4：measured.json 与本次独立复核的三个 episode 全部 ≤1257，没有一个超过 1301 —— 与计划原文矛盾**。
- **PickXtimes xhard2**：计划原文完全未列入会超预算的档位，但 measured.json 与本次独立复核显示
  ep0 恰好达到 1350（>1300），ep3=1281、ep6=1275（<1300）——即该档在 3 个样本里有 1 个已经超出
  冻结评估预算，计划的「会超预算」清单遗漏了这一档（哪怕只是偶发）。

## 与原生档对照

`measured.json` 中全部 native（easy/medium/hard）cell 的最大 `n_steps`=1027
（VideoRepick hard ep3），最大 `exec_steps_to_completion`=905（BinFill hard ep3），
两者都远低于 1300/1301，说明该问题在原生档完全不存在，只在新档（xhard1-4）出现，
属于 new_tier_only。

## 判定行

`VERIFY=CONFIRMED finding=crosscut-values-04 category=new_tier_only severity=low confidence=high`
