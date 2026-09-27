# P5 探针报告：VideoUnmaskSwap / ButtonUnmaskSwap，V4 环带 10 个干扰容器 + 外环随内环同步交换

日期 2026-09-24。在 worktree `/data/hongzefu/robomme_v5_probe_wt`（提交 581efec）里用进程内 monkeypatch 与离线副本完成，
未修改任何被 git 跟踪的文件。本文由主会话根据探针 agent 的最终汇报与本目录原始数据整理（agent 的报告全文在回传时被截断）。

## 规则（V5 计划 1.4 的 L16～L23 结论）

- 干扰容器：V4 环带 `[0.2675, 0.45]`，count 10，含 cube [5,5]，统一 OBB 间距、精确 8 角点可见性、三色平衡轮转、1024 次、带序号命名。
- 外环交换：每个内环窗口恰好一次；发起者 `randperm(10)` 全体轮转；搭档取干扰容器中 XY 最近邻；候选不可行按排列换下一个发起者，全不行整段重抽干扰布局，最多 16 次。
- 可行 = 两对联合连续碰撞证明（复用 `_prove_pair`）+ 外环路径全程在画面内 + 离每个内环容器圆距 ≥ 0.04 + BUS 离两个按钮中心 ≥ 0.122；lane 0.07；认证预筛开启。
- 内环对内环扫掠在 reset 预判拒绝；内环搭档仍运行时解析。

## 校验（`verify_offline.log`、`cmp_prefilter.log`、`sim.log` 的 `ROW` 行）

- 离线副本对 v4-01 冻结规格 20/20 逐值一致。
- 单对联合检查与 `check_swap_sweep` 48/48 一致；可见性判据与精确判据 0/20000 不一致。
- 预筛开/关判定 72/72（每环境 36）不变。
- 原型 reset 的干扰放置与交换对与离线逐值相同。
- V4 实跑碰撞局 VUS seed 4500300 在 reset 的 sweep#1 被预判拒绝，位置与 V4 实跑一致。

## 离线联合可行性（每环境 500 局，`offline_main.log` 两行 `SUMMARY`，明细 `offline_*_main.jsonl`）

| 指标 | VUS | BUS |
|---|---|---|
| 首次干扰布局可行率 | 99.8% | 98.9% |
| 平均重抽次数 | 0.002 | 0.011（最多 1 次） |
| 16 次耗尽 | 0 | 0 |
| 第一候选发起者就可行的窗口 | 62.6% | 48.3%（主要被可见性与按钮距离挡掉） |
| 内环对内环 reset 预判拒绝率 | 0.8% | 9.8% |

与计划 2.5 联合表「V4 环带 10 个带回退 100%/100%」相比，首次可行率低 0.2 / 1.1 个百分点，靠重抽补到 100%，结论不变。

## 原型演示（`sim.log` 的 `DEMO` 行，录像与 h5 在 `demo_out_*`）

- 6/6 成功（VUS 3、BUS 3），BinCollisionError 0。
- 外环容器终点误差 ≤ 0.16 mm；外环 cube 跟随误差 ≤ 0.14 mm；外环容器全程在画面内。
- reset 墙钟：预筛开 VUS 1.4～1.9 s / BUS 1.3～1.6 s；预筛关 VUS 34～55 s / BUS 23～33 s。
- 每步耗时 p95 约 290 ms；`hold.log` 的空跑诊断显示与外环 cube 停放点堆叠无关，根因未定位。

## 判定行

```
SWAP10=REPORT VUS_first=0.998 BUS_first=0.989 fallback_mean=VUS0.002/BUS0.011 exhaust16=0/0 inner_reject=VUS0.008/BUS0.098 reset_s_prefilter_on/off=VUS1.4~1.9/34~55,BUS1.3~1.6/23~33 demo_ok=6/6 bin_collision=0
```

## 结论与盲区

- 方案可行，数量 10 与外环交换规则可直接进实施。
- 预筛必须覆盖三处检查（内环预判、外环规划、运行时复核），否则抽签每环境要多 5～7 分钟。
- 每步 290 ms 的根因要在实施时复查；按钮与手臂仍不在碰撞模型里；样本量为每环境 3 局演示。

## 文件索引

`swap10lib.py`、`proto_sim.py`（规则实现，文件头有注释）、`run_sim.sh`、`offline_main.log`、`offline_*_main.jsonl`、`offline_pf0.log`、
`verify_offline.log`、`cmp_prefilter.py/.log`、`sim.log`、`hold.log`、`frames/`、`demo_out_VideoUnmaskSwap/`、`demo_out_ButtonUnmaskSwap/`（约 3.2 GB）。
