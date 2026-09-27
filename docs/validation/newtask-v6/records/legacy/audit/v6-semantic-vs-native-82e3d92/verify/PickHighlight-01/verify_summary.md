# PickHighlight-01 独立复核记录（AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1）

结论：CONFIRMED，category=new_tier_only 成立。

独立复核（不复用 grounded_scan.json 结论，重新从 h5 源与代码源读取）：
1. verify_grounded_text.py：直接读取 xhard2/ep6[480,585]、xhard3/ep3[701,820]、xhard4/ep0[785,908] 三段
   grounded_subgoal 全程无 `<`坐标`>`，与 finding 完全一致；online 版本在同一区间部分帧仍带坐标
   （如 xhard2 ep6 t478-500 online=`<85,123>`），证实是"offline 填充"特有缺陷。
2. records_raw.json 交叉核对：仅这 3 个 episode 带 success_NO_OBJECT_*.mp4 伴生文件。
3. verify_projection.py：用 proj_test.py 同款相机内外参投影法重算三个目标方块像素坐标，
   与 finding 给出的数值逐位相同：xhard2 cube1→(122.3,88.4)，xhard3 cube8→(92.2,56.5)，
   xhard4 cube0→(118.4,56.0)；均与同步 choice_action.point（[88,122]/[57,92]/[56,118]，xy互换）吻合。
4. highlight_ids 序数换算核对：xhard2 ep6 highlight_ids=[2,7,1,5,0]→第3个=index2=cube1；
   xhard3 ep3 highlight_ids=[5,3,4,1,8,2]→第5个=index4=cube8；
   xhard4 ep0 highlight_ids=[3,4,9,2,0,1,8]→第5个=index4=cube0。全部与 finding 一致。
5. verify_grasp_distance.py：抓取时刻 eef 平面位置与目标方块初始 xy 的欧氏距离分别为
   0.00437m / 0.00503m / 0.00496m，均 ≤0.006m，证实策略确实抓对了目标（问题只在文本层无法定位）。
6. 帧截图 xh2ep6_t470/478/480/500/553.png 等：切换帧附近机械臂位于前一放置点附近，
   与"上一放置动作的机械臂遮挡下一个目标"的机制描述相符（视觉上不冲突，但非逐像素分割级证据）。
7. 代码锚点核实（git show AUDIT_BASE）：
   - src/robomme/env_record_wrapper/RecordWrapper.py 确有 previous_subgoal_segment /
     current_subgoal_segment_filled / no_object_flag / no_object_video_frames 机制，
     process_segmentation 在 subgoal 切换时一次性填充 offline 文本。
   - src/robomme/robomme_env/PickHighlight.py 确有 xhard 专属
     subgoal_color_suffix="omit"（2026-09-22 用户定稿"整段去掉"），只对 xhard 生效。
8. 原生档核对：9 个 native episode 的 grounded_no_coord_runs 全部为空（0/9），且 pick 文本
   均带 `, which is {color}` 后缀；xhard 档（即使坐标存在时）从不带颜色后缀，与 J4 一致。
9. 计划文件核对：git show AUDIT_BASE:0925-newtask-release-v6-plan.md 第三、四节
   （四档定稿表、逐环境定稿，含 PickHighlight 专节）及风险登记（四、风险登记 8 条）均未提及
   "遮挡导致 offline grounded_subgoal 整段无坐标"这一后果，证实 finding 所称
   "plans do not mention coordinate loss" 成立。

未发现足以反驳该 finding 的证据；category 判定：new_tier_only 成立的关键在于
该缺陷的"完全不可定位"效果（无坐标+无颜色）只能在 xhard 出现——因为 native 档
即使坐标缺失（实测中从未发生）也总有颜色后缀兜底；纯坐标缺失机制本身其实是
RecordWrapper 通用逻辑（native/xhard 共用同一段代码），只是 native 9 个样本中概率上未触发。
severity=low、confidence=high 与实测证据强度相符（3/12，非系统性但确凿可复现）。
不构成任何已排除项（F1-F6/D1-D7/左右措辞/纯网站文案）的重复。
不需要新仿真即可确认（已用现有数据完整复核）。
