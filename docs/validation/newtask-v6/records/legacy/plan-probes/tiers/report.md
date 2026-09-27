# 探针 E：V6 新档 xhard1/2/3 在 greatlakes 上的真演示实测（2026-09-25）

仓库 newtaskRelease-v5；未改任何被 git 跟踪的文件。subagent 建好配置与 driver 并起跑后中途交回，主会话接手：两次续跑、修 driver、汇总、出图、写本报告。

## 一、方法
- 新档一律沿用 xhard 机制、只内插数值，所以用 `difficulty="xhard"` + `sampling_config` 覆盖 decision 数值模拟每个新档（`make_configs.py` → `configs/<task>_<tier>.json`，52 份，含 13 份现行 xhard 对照）。守卫 `assert_native_decision` 只比键结构不比数值，52 格全部放行，**无需 patch**。
- 每格 6 局（seed `9_000_000 + env_code*10_000 + tier*1000 + i*101`），每环境另 3 局 xhard 对照，共 273 局。逐局直接调 `generate_dataset_newseed._worker`（录像器、规划器、失败分类与正式生成相同），产物写节点 `/tmp` 读完即删，只留结果 jsonl。
- GL：占位 job 61890467 内 `srun --overlap`，A40。第一次 16 worker、第二次 8 worker 都在 worker 换代点（16×3=48、8×3=24 局）挂死——原因是 driver 的 `ProcessPoolExecutor(max_tasks_per_child=3)` 在 spawn 上下文下换代挂死（cgroup 无 OOM 记录，峰值内存 95 GB / 上限 206 GB）；去掉该参数后 12 worker 续跑 201 局 1026 s 完成。三段日志 `run_gl.log`、`run_gl2.log`、`run_gl3.log`。
- 已知代测：VUS 的交换/pick 次数实际读 `native.parameters.configs[档]`（decision 键无人读），配置里显式给出后生效；VPB/VPO 现行 xhard 路径只支持 `return_to_origin`，(k2,不放回) 与 `return_last_only` 用 (k2,全放回) 代测上界，VPO xhard2 的 v 上界 3 靠 driver 进程内补丁；VUS/BUS 外环含 cube 数取干扰数一半。

## 二、结果（`tables.md` 全表、`summary.json`、`tiers_summary.png`）

演示级成功率（成功 / reset 通过局）：13 环境 × 3 档共 39 格，**37 格 100%**；例外 BinFill xhard1 5/6、xhard3 4/6（DatasetGenerationError，与 xhard 对照 2/3 同类）。

reset 失败（SceneGenerationError，均为既有拒绝率）：VR xhard1/2/3 各 2/3/1 局（≈60%，与审计 0.625 一致）；VPB xhard1 2、xhard2 1（xhard 对照 2/3）；VPO xhard1 3、xhard2 5、xhard3 5（xhard 对照 2/3；VPO 的 Target 4 放不下问题）；PH、VUS 的 xhard 对照各 1。

步数（成功局，中位/最大）与评估 1301 步（非演示步）：
- 超 1301 的格：PickX xhard2 1/6 局（1341）、xhard3 5/6 局（中位 1577、最大 1714）；xhard 对照 2/3 局（最大 2163）。其余 12 环境全部 ≤1301（RS xhard1 总步 1316 但非演示步 500）。
- 新档总步数全部低于各自 xhard 对照（PL 824/1166/1326 对 1720；RS 1316/1473/1718 对 2220；VR 885/1200/1419 对 1625；PickX 994/1204/1577 对 1955；BUS 494/615/648 对 692；VUS 531/687/710 对 806）。
- 单局墙钟中位 24～140 s，最大 161 s；无 fail_safe 5000。

难度旋钮（各局实抽均值）逐档严格上升：BinFill 4.2/4.5/5.2（X 5.3）、PickX 6.3/7.5/9.5（10）、SwingX 3.3/4.7/6.3（6.3）、PH pick 4/4.8/5.5（6）、VU 8/10/13（15）、BU 7/9/12（14）、VUS 4.3/6.2/7.5（10）、BUS 3.5/4.5/5.5（7.3）、VR 3.8/5.7/7.2（10）、PL 10/15/18.7（25）、RS 9.5/11.5/13.7（18）；VPB k 1/2/2/2、VPO 访问总数 3/6/8（X 7，n=1，代测配置等于 xhard）。

## 三、结论
1. 三个新档在真实演示链路上都能生成：演示级成功率与 xhard 持平或更高，失败全部来自各环境既有的 reset 拒绝（VR/VPB/VPO）与 BinFill 的原有演示失败类型。
2. 步数满足口径 2「新档不超过 xhard」；PickXtimes 的 xhard2/xhard3 会像 xhard 一样超评估 1301 步（V5 现状，计划 1.3 已记）。
3. 单调性在 11 个有独立旋钮的环境上成立；VP 两环境用代测配置，真正的三档要以 vp 副本的放回策略实现为准（M11）。
4. 跑 GL 多 worker 时 driver 不要用 `max_tasks_per_child`（spawn 上下文换代挂死）。
