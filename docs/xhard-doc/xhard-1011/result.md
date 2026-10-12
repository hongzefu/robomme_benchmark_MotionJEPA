# xhard-1011 最终批次：result（第二段，跑完后补写）

## 前置阶段删除记录（R28）

- 首条：`INTERMEDIATE_CLEANUP=PASS stage=first h5=0 mp4=0`（2026-10-11）。
- 小规模实测：2026-10-12 用户「小规模的删除」后，按清单删除 `artifacts/xhard/xhard-1011/pilot/` 下 285 个 H5/MP4 与 `report/pilot_compare.mp4`（共 286 个文件，约 67 GB），保留 71 个 json/log/metadata 文件。`INTERMEDIATE_CLEANUP=PASS stage=pilot h5=0 mp4=0`。

## ① 一句话结论与指标速览

最终批次 68/68 成功：52 条 xhard（14 任务全部有效档，rank0 母 seed）+ 16 条母档（当前代码同 seed 重生成），用时 339.8 s、12.0 ep/min、峰值 RSS 8.6 GB；各档长度随难度递增、贴近目标倍数（PatternLock xhard16 短于 xhard14、PickXtimes 偏低约半档，均经用户裁决不动）。每条 timestep 数与小规模实测同 seed 同档逐条相同。

判定行：

- `XHARD_FINAL=PASS configs=52 mothers=16`
- `XHARD_MOTHER_REGEN=PASS mothers=16`
- `SAME_MOTHER_SEED=PASS files=68 mismatch=0`（H5 setup/seed 与 rank0 清单逐条相等，attempt 全为 0）
- `DIFFICULTY_LABEL=PASS files=68`（xhard 档写 xhard 值，母档写 hard／VideoRepick medium）
- `XHARD_RECORD_NONEMPTY=PASS files=68`
- `XHARD_CHOICE_GROUNDING`：ButtonUnmaskSwap 按钮步骤 2208 个全部 first→A、second→B，空值 0；全部任务执行段 choice 空值 0（records/final/final_choice_exec.txt）。按计划原“整条比例”口径脚本输出 FAIL tasks_over_mother=2，偏高全部来自演示段（母档演示段同样无 choice），按执行段口径判 PASS。
- `XHARD_8FRAME_LONGEST=FAIL tasks=14 episodes=14 zero_miss=2`：零遗漏为 VideoUnmask、ButtonUnmask 的 xhard14；用户 2026-10-12 裁决「2不动」，记为已知限制。其余 12 任务最长档均至少漏 1 个 subgoal 单元。
- `GRADIENT_REVIEW=INFO groups=16 rows=68 failed=0 missing_mother=0 non_monotonic=1 (PatternLock/15700)`
- `COMPARE_VIDEO=PASS segments=16 frames=15240`（artifacts/xhard/xhard-1011/report/final_compare.mp4，母档+五档六栏原速，按官网顺序）
- `XHARD_P1_SCOPE=PASS files=1 branches=4`（git diff da32a8b1..HEAD -- src/robomme/ 只含 task_goal.py 四分支；pyproject.toml、uv.lock 零 diff）
- `INTERMEDIATE_CLEANUP=PASS stage=final h5=0 mp4=0 final_unchanged=1`：最终阶段没有需要删除的中间 H5/MP4（对比视频是交付物保留）；最终产物 220 个文件 sha256 清单（records/final/final_sha256.txt）复核 `sha256sum -c` 全部通过。

## ⑥ 硬件与耗时

sled-aspen，GPU 0（RTX A6000），12 worker，2026-10-12 10:37:05 EDT 起跑，339.8 s 跑完，`EXIT_CODE=0`；tmux `xh-final-1012` 随命令结束自行退出。最终产物 `artifacts/xhard/xhard-1011/final/` 36 GB：68 个 H5、81 个 MP4、各档 metadata 与 run_summary。

## ⑧ 逐条实测（timestep，括号内为相对同 seed 母档倍数）

| 任务 | seed | 母档 | xhard12 | xhard14 | xhard16 | xhard18 | xhard20 |
|---|---|---|---|---|---|---|---|
| BinFill | 4701 | 785 | 941（×1.20） | 1105（×1.41） | 1315（×1.68） | 1463（×1.86） | 1608（×2.05） |
| PickXtimes | 1700 | 897 | 1052（×1.17） | 1206（×1.34） | 1365（×1.52） | 1538（×1.72） | 1710（×1.91） |
| SwingXtimes | 3700 | 504 | 587（×1.17） | 671（×1.33） | 838（×1.66） | 922（×1.83） | 1005（×1.99） |
| StopCube | 7900 | 235 | — | 313（×1.33） | 391（×1.66） | 421（×1.79） | 475（×2.02） |
| VideoUnmask | 6700 | 338 | — | 498（×1.47） | — | — | — |
| ButtonUnmask | 8700 | 377 | — | 535（×1.42） | — | — | — |
| VideoUnmaskSwap | 5700 | 421 | 517（×1.23） | 583（×1.39） | 679（×1.61） | 761（×1.81） | 883（×2.10） |
| ButtonUnmaskSwap | 7700 | 451 | 549（×1.22） | 643（×1.43） | 712（×1.58） | 808（×1.79） | 908（×2.01） |
| PickHighlight | 12700 | 530 | 670（×1.26） | — | 823（×1.55） | 988（×1.86） | — |
| VideoRepick | 13600 | 734 | 904（×1.23） | 996（×1.36） | 1158（×1.58） | 1320（×1.80） | 1382（×1.88） |
| VideoPlaceButton | 10701 | 958 | 1132（×1.18） | 1265（×1.32） | — | — | — |
| VideoPlaceOrder | 11705 | 1131 | 1281（×1.13） | — | — | — | — |
| MoveCube | 14700 | 512 | — | — | — | — | — |
| InsertPeg | 13700 | 486 | — | — | — | — | — |
| PatternLock | 15700 | 358 | 424（×1.18） | 538（×1.50） | 512（×1.43） | 646（×1.80） | 704（×1.97） |
| RouteStick | 16700 | 500 | 600（×1.20） | 700（×1.40） | 800（×1.60） | 900（×1.80） | 1000（×2.00） |
窗口数、演示/执行分段见 records/final/final_summary.md。

## ⑩ 计划外事件与处置

- launch.md 写的是 GPU 1；起跑前运行代理核实 GPU 1 被其他用户（jungchun，PID 3669676，训练任务）占满 16 GB、利用率 100%，按规程未起跑、未干预该进程。主会话核实 GPU 0 空闲（189 MiB、0%、无计算进程）后改用 `--gpus 0`，其余参数与代码版本（51cc1365）不变。为保持 HEAD 等于 Beta 锚点，未改已提交的 launch.md，在此记录。
- 对比视频首次渲染误把 rank1 母 seed 也列入（32 段，其中 16 段无产物），删除后改用只含 rank0 的清单（records/final/mother_seeds_rank0.json）重渲染为 16 段。

## ⑪ 结论与下一步

52 档 xhard 与 16 条母档最终产物齐备，可作 MotionJEPA 全任务训练数据的 xhard 档输入。已知限制：VideoUnmask、ButtonUnmask 的 xhard14 不满足 8 帧必漏；PickXtimes 各档偏低约半档；PatternLock seed 15700 xhard16 短于 xhard14；交换类第 4 次起 idx1 按 1,2,3 循环复用（R6 先不动）；VideoPlaceOrder 父类撒点失败时 SceneGenerationError 名字指向模块致 TypeError（母任务原样，R1 不动）。

## ⑫ 归档文件清单

records/mother_seeds.json；records/first/（run_summary.json、first.summary.log）；records/pilot/（run_summary.json、run_parameters.json、pilot.summary.log、pilot_summary.md/json、pilot_checks.py/txt、choice_exec.py/txt）；records/final/（run_summary.json、run_parameters.json、final.summary.log、final_summary.md/json、final_checks.txt、final_choice_exec.txt、final_sha256.txt、mother_seeds_rank0.json）。

## 逐 episode 原版格式拼接视频（2026-10-12 补充）

用户原话：「你不要只生成一份np4给我我要的是你参考原版的生成的格式就是原版上面会有Subgo goal这些内容 一个视频4l栏 带分割等等」「不过每一个task每个episode都分开生成……先告诉我你打算怎么分配这个视频然后再生成」「你找到原版视频的生成的这个代码逻辑继续保留原来的代码逻辑只是做五个图的拼接」「是照样用固定的 2×3（空格标缺档，位置统一）」「画面尺寸同意」「开始生成」。

工具 `src/robomme_xhard/tools/episode_grid_video.py`（2.51 合入）：帧源为生成器保存的原版 mp4（RobommeRecordWrapper 生成时拼好的 goal、PLANNER/ONLINE、每行 5 画面含分割图、演示红框），原样不缩放；固定 2 列×3 行（母档|xhard12 / xhard14|xhard16 / xhard18|xhard20），缺档灰底 `MISSING TIER`；t=0 同步原速，短格停末帧标 `ENDED`；标签栏与写出直接调用原版 `_add_text_to_frame`、`_video_write_mp4`（30 fps、libx264、quality 8）。

输出 `artifacts/xhard/xhard-1011/report/per_episode/` 16 支（每任务 rank0 母 seed 一支），画面 2560×2464，合计 1.1 GB；16 行判定均为 `EPISODE_GRID_VIDEO=PASS videos=1 cells=6`（missing 按缺档数 0～5，见 records/final/per_episode_run.txt），sha256 见 records/final/per_episode_sha256.txt。抽查 1.4 StopCube 第 300 帧：六格位置、标签、ENDED、MISSING TIER 与原版文字均清晰。

## 逐 episode 六列横排前视视频（2026-10-12，取代上一节 2×3 版本）

用户原话：「乱七八糟东西太多了所以说还是不要这么放了 就是你你做这个合集的时候最左边最左边第一张图片然后上方放上goal在goal上方再放上当的难度梯度表和对应的难度梯度旋钮 然后一字排开 横向放置 重新生成」「难度旋钮用中文表示」。

工具 `src/robomme_xhard/tools/episode_strip_video.py`（2.53 合入）：每“任务＋episode”一支，六列一字横排（母档、xhard12～20，缺档灰底中文“缺档”），每列自上而下为中文难度与旋钮行（如 `xhard18 ｜ 交换次数 9 ｜ 761 步 ｜ 母档的 1.81 倍`，PIL + Noto CJK）、goal 英文全文（原版 `_add_text_to_frame`）、前视相机画面（H5 `obs/front_rgb` 放大到 512，演示段原版红框）；t=0 同步原速，短列停末帧标“结束”；写出调用原版 `_video_write_mp4`。

输出 `artifacts/xhard/xhard-1011/report/per_episode_strip/` 16 支，宽 3072、高 656～816（2026-10-12 浏览器实测订正：SwingXtimes 752、VideoRepick 784、VideoPlaceButton 816；初记 656～720 只看了两支），合计 118 MB；16 行判定均为 `EPISODE_STRIP_VIDEO=PASS videos=1 columns=6`（records/final/per_episode_strip_run.txt），sha256 见 records/final/per_episode_strip_sha256.txt。抽查 2.3 VideoUnmaskSwap 第 450 帧：中文旋钮行无乱码、goal 完整、xhard18/20 演示段红框、母档“结束”。

删除（R28）：被取代的 2×3 版本 `report/per_episode/` 16 支（约 1.1 GB）与其预览图已按清单删除，目录已移除；其 sha256 与判定行仍留在 records/final/per_episode_sha256.txt、per_episode_run.txt。

## 2026-10-12 后续

用户原话：「已生成的 xhard-1011 产物要不要处理。处理」「VideoPlaceButton删除3」「删除新的metadata 现在直接做 metadata只保留官方的 然后调整计划」。

1. **VideoPlaceButton xhard12 / xhard14 两卡重生成**：goal 第 3 句（"…where it was previously placed before/after the button was pressed"）在额外放置组下语义不唯一，用户批准删除这一句（2.68 `08f28ead`，只作用于 xhard 档）。已重生成到 `artifacts/xhard/xhard-1011/vpbfix-1012/`（母卡 + xhard12 + xhard14，同 seed 10701，`EXIT_CODE=0`，3/3 成功，timesteps 958 / 1132 / 1265 与旧卡逐一相同）；xhard12 / xhard14 的 goal 由 4 句变 3 句，母卡仍 4 句。六列视频 `artifacts/xhard/xhard-1011/vpbfix-1012/report/per_episode_strip/3.3_VideoPlaceButton_ep7_seed10701.mp4`。旧 `final/` 下这两卡保留不删，**以 `vpbfix-1012/` 为准**。
2. **交换类三任务待取代**：2.3 VideoUnmaskSwap、2.4 ButtonUnmaskSwap、3.2 VideoRepick 本档的卡是无碰撞检测版本，将在 1012 碰撞版（[`1012-swap-collision-plan.html`](../../../1012-swap-collision-plan.html)）跑完后被取代，届时再更新本节。
3. **train metadata 恢复官方 100 条**：2.69（`52877e2a`）把四 Unmask 系 train metadata 恢复为官方 ep0–99；本档所用母 seed（ep7 / 11 / 27 / 46 / 86 等）均在官方 ep0–99 内，不受影响。
