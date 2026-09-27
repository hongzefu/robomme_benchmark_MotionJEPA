# VideoPlaceButton-03 独立复核

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1（只读 `git show`，未改动工作树/仓库）。

## 结论：CONFIRMED

## 独立证据链（全部本轮重新产出，未直接照抄前审查结论）

1. **代码机制（`git show` 读取）**：
   - `src/robomme/robomme_env/VideoPlaceButton.py::_xhard_pick_place` home 分支：
     `segment_text = "put the cube back to its original position at <>"`。
   - `src/robomme/robomme_env/utils/xhard_home_site.py::build_home_sites`：用
     `build_gray_white_target(radius=env.cube_half_size, ...)` 在方块初始位姿上建落点，
     `env._hidden_objects.append(home)`。
   - `_hidden_objects` 在整个 git 树内（`git grep -rn "_hidden_objects" <AUDIT_BASE>`）只在
     `xhard_home_site.py`、测试与文档里出现，`src/robomme` 自身从未消费它。
   - 追到外部依赖 `mani_skill`（`.venv/lib/python3.11/site-packages/mani_skill/envs/sapien_env.py`
     `_get_obs_sensor_data`）：每次采集 sensor 数据前对 `self._hidden_objects` 逐个
     `obj.hide_visual()`，随后同一次调用里连 `rgb`/`depth`/`segmentation` 一起从
     `sensor.get_obs(...)` 取出——即 **home 落点被无条件、逐帧地从 base_camera 的
     segmentation 通道剔除，不是偶发遮挡，是确定性排除**。
   - `src/robomme/robomme_env/utils/segmentation_utils.py::process_segmentation`：
     目标 id 不在 mask 里 → `compute_center_from_ids` 返回 `None` → `missing_placeholder=True` →
     整段文字回退为 `current_task_name`（即不含 `<>` 的 `"put the cube back to its
     original position"`）。三步机制逐环相扣，找齐了"为什么"。

2. **交付数据独立扫描**（`scan.py`，读 `new-tier-index.json` 里全部 12 个 VideoPlaceButton
   xhard1-4 H5，不复用前审查的 json）：
   - `HOME_TEXT_COUNTER = {'put the cube back to its original position': 18}` ——
     12 个 episode 共 18 段 home-return，**全部**无坐标，与 finding 所述 18/18 一致。
   - 同批文件里的 `drop the cube onto target at <r,c>` 段绝大多数带坐标（示例见
     `scan_result.json`），证明并非 grounding 全局失效，只有 home 落点这一类系统性缺失。

3. **原生档对照**（`scan_native.py`，独立读 9 个原生 `VideoPlaceButton_episode_*`
   H5，未复用任何审查中间产物）：全部 9 个都用 `drop the cube onto table`（无 `<>`）
   作为终局演示落点文本，**原生档从未承诺坐标、也就谈不上"未兑现"**——与
   finding 的 native_behavior 描述（9/9）一致。

4. **视频/图像独立核验**（不同于前审查的 `vpb_track.py`，本轮另写
   `track_home.py` / `crop_compare.py`）：
   - xhard1 ep0（红方块）：用局部窗口红色阈值分别在 t=0（首次拿起前）与 t=840
     （home 段结束、`static` 之前）估质心，`LOCAL_DIST≈3.79px`；`crop_t0_vs_t840.png`
     目视两帧方块位置几乎重合，且两帧内均看不到任何落点标记（与上面"逐帧强制隐藏"
     的机制结论吻合，不是偶发遮挡）。
   - 复核前审查 `crop_x4e0_home_green.png`（xhard4 ep0 绿方块 5 帧时间轴）：t=0 与
     t=1407（回到原位后）方块像素位置几乎相同；中间帧（方块离开原位期间）原位处
     完全没有任何落点标记痕迹——直接印证"无条件隐藏"而非"被方块自身遮住"。

## 计划依据核查

`git show <AUDIT_BASE>:0925-newtask-release-v6-plan.md` 中 D8 决议、第三节数值表、
第四节 VPB/VPO 落地记录只讨论"是否放回原位"（`return_to_origin`）与放台次数梯度，
**未提及 home 落点是否会/应当在 grounded 文本里给坐标**。即该 mismatch 没有计划依据
支撑，属未预期的副作用。

## 排重

对照 EXCLUDED 清单（F1-F6、VPB 终局绑定项、D1-D7、left/right、纯网站文案）逐条核对，
均不涉及"home 落点坐标缺失"这一具体机制，非重复项。

## 类别判定：new_tier_only（同意 finding 原判）

原生档（easy/medium/hard）VPB 的终局演示落点固定走 `drop the cube onto table`（原三档
`native_random_goal_site` 策略），从不使用 `_xhard_pick_place(home=True)` 分支、也从不
生成带 `<>` 的 "original position" 文本——该 mismatch 的两个必要条件（home-return 模板 +
`build_home_sites` 隐藏机制）都只在 `xhard1-4` 的 `return_to_origin` 路径上出现，原生档
不具备复现该问题的代码路径，故不是 native_same。

## 严重度/置信度

同意 finding 的 low/high：功能上不影响任务成功判定（`is_obj_dropped_onto` 只看水平
距离，不依赖 grounded 文本），影响面局限于"以文本坐标监督/评估落点定位"这一下游
用途，且是确定性、可复现的系统性行为（不是偶发）。

## 是否需要新仿真

不需要。全部证据来自已交付的 H5/JSON（读 HDF5、`git show`、读外部已安装
`mani_skill` 包源码），未运行任何仿真、未导入 `robomme`/`gymnasium`/`sapien`/`mani_skill`
的环境代码，只用 `h5py`/`numpy`/`PIL` 读取。
