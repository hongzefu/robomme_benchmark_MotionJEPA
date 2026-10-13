# 交换配对第二版：全量结果

## 一、结论与指标速览

已完成计划阶段 E 的全部 180 个身份：160 条任务成功、20 条正常碰撞拒绝、基础设施失败零；拒绝身份不换 seed、不补跑。30 支六列视频及逐母 seed 的 v1/v2 对比报告已生成。**本轮成功数比 v1 的 165 少 5，不能解读为成功率提升。**

| 官网编号 | 任务 | 母档成功 | xhard 成功／计划 | 正常拒绝 |
|---|---|---:|---:|---:|
| 2.3 | VideoUnmaskSwap | 10／10 | 50／50 | 0 |
| 2.4 | ButtonUnmaskSwap | 10／10 | 45／50 | 5 |
| 3.2 | VideoRepick | 10／10 | 35／50 | 15 |

`XHARD_FULL_DERIVE=DONE expected=180 seen=180 missing=0 dup=0 unknown=0 ok=160 task_reject=20 infra=0`

`REPORT_V1V2=PASS seeds=30 rows=180`

`EPISODE_STRIP_VIDEO=PASS videos=30 columns=180 missing=0`

`DIFFICULTY_LABEL=PASS files=160`

`XHARD_RECORD_NONEMPTY=PASS files=160`

`FULL_VIDEO_METADATA=PASS videos=30 width=3072 fps=30`

`OLD_RUN_INTACT=PASS files=426 mismatches=0`。完整 sha256、字节数、文件数与只读状态均通过，证据见第八节。

## 二、版本与代码状态

全量与报告起跑版本都是 `f98c779a2c3f086759d9fcc4663a06da7deec083`（2.98Beta）；起跑时工作区干净。从生成起跑到视频、汇总、对比包装结束没有修改源码、依赖、配置、参数或 HEAD，包装结束时再次验证工作区干净。

源码与通过四卡 smoke 的 `e6e2d1e5d2ab6a428b271d92cd0e476480c59a68` 相同；`src/robomme/` 与代码基线 `0ec9951b` 零差异。证据：[full_source_freeze.json](records/full_source_freeze.json)。`SOURCE_FREEZE=PASS`、`SRC_ROBOMME_ZERO_DIFF=PASS`。

Beta 永久保留，结论以配对的 2.98 独立提交回写，不 amend 或 squash。当前完整实施口径见根目录 [1012-swap-pairing-v2-plan.html](../../../1012-swap-pairing-v2-plan.html)，前置验证见 [smoke 结果](../xhard-1012-swapv2-smoke/result.md)。

## 三、启动与配置还原

完整生成命令、环境、预算、运行型代理权限及起跑前判据见 [full-launch.md](full-launch.md)。该文档从 Beta 可恢复：`git show f98c779a2c3f086759d9fcc4663a06da7deec083:docs/xhard-doc/xhard-1012-swapv2/full-launch.md`。

| 覆盖项 | 固定值 |
|---|---|
| UV_CACHE_DIR | `/home/hongzefu/.cache/uv` |
| PYTHONUNBUFFERED | `1` |
| 环境 | VideoUnmaskSwap、ButtonUnmaskSwap、VideoRepick |
| 档位 | xhard12、xhard14、xhard16、xhard18、xhard20，另含母档 |
| GPU／worker | GPU0／32 |
| 重试 | attempt=0，retry_on_failure=false |
| 线程／进程回收 | limit_threads=true，max_tasks_per_child=8，affinity=none |
| 录像 | save_video_for_recording=true |
| 生成墙钟上限 | timeout 3600s |

生成 tmux 会话 `xh-swapv2-full-1012`，启动时间 2026-10-12 21:57:48（美国东部时间）；包装会话 `xh-swapv2-report-1012`，22:09:31 启动、22:14:22 结束。包装只读已有产物，不做 GPU 仿真。两个会话均已自然结束，未取消其他会话。

包装入口依次为 `robomme_xhard.tools.summarize`、`episode_strip_video`、`swap_v2_report`，完整命令如下，实测输出见 [包装日志](records/full_report.summary.log)。输出统一到新 `artifacts/xhard/xhard-1012-swapv2/report/`，未覆盖旧轮报告。

```bash
export UV_CACHE_DIR=/home/hongzefu/.cache/uv PYTHONUNBUFFERED=1
uv run --no-sync python -m robomme_xhard.tools.summarize --root artifacts/xhard/xhard-1012-swapv2/full --seeds artifacts/xhard/xhard-1012-swapv2/mother_seeds_all.json --out-md artifacts/xhard/xhard-1012-swapv2/report/summary.md --out-json artifacts/xhard/xhard-1012-swapv2/report/summary.json
uv run --no-sync python -m robomme_xhard.tools.episode_strip_video --root artifacts/xhard/xhard-1012-swapv2/full --seeds artifacts/xhard/xhard-1012-swapv2/mother_seeds_all.json --out-dir artifacts/xhard/xhard-1012-swapv2/report/per_episode_strip
uv run --no-sync python -m robomme_xhard.tools.swap_v2_report --v1 artifacts/xhard/xhard-1012-coll/full --v2 artifacts/xhard/xhard-1012-swapv2/full --seeds artifacts/xhard/xhard-1012-swapv2/mother_seeds_all.json --out-md artifacts/xhard/xhard-1012-swapv2/report/v1_vs_v2.md --out-json artifacts/xhard/xhard-1012-swapv2/report/v1_vs_v2.json
```

## 四、输入与划分口径

三任务各十个固定母 seed，每个母 seed 展开一母档加五档，共 180 个身份。VideoUnmaskSwap、ButtonUnmaskSwap 的母档来源 hard，VideoRepick 来源 medium；官方 HF revision 未核的状态保留。没有官方参考集下载、额外 reset 对拍或分布采样。

母清单 [full_mother_seeds.json](records/full_mother_seeds.json) 的 sha256 为 `56a0381bb78485a7373f6446a4a0007679c0aff3e5a0c347ad3c16528200e278`，起跑后再次核对相同。生成器使用的完整参数与 180 个身份的结果保存在 [full_run_compact.json](records/full_run_compact.json)。

## 五、交换配置与均衡

沿用已批准的 V9 `score=max_sum`、`budget=20`、`accept_range=1`、`forbid_undo=true`；最长交换序列仅规划一次，五档取对应前缀。没有更改碰撞阈值、按钮包络、槽位绑定或成功字段语义。

成功 xhard 档的最长序列极差：VideoUnmaskSwap 50 条均为 1；ButtonUnmaskSwap 45 条均为 0；VideoRepick 35 条均为 0。短档前缀极差：VideoUnmaskSwap 为 0×10、1×40；ButtonUnmaskSwap 为 0×36、2×9；VideoRepick 为 0×7、1×28。计划只保证最长序列，前缀不单独保证极差 ≤1，因此如实保留极差 2。

对比报告的分布还包含有规划证据的失败卡；与这里限定「成功 xhard」的分母不同，不能直接混算。净置换恒等比例只在有完整规划证据的身份中计算，母档与 reset 时拒绝的身份保持未知；逐档分母见 [full_v1_vs_v2.json](records/full_v1_vs_v2.json)。

## 六、硬件、存储与耗时

本机 sled-vail，RTX 6000 Ada GPU0、本机 NVMe、32 worker。生成器墙钟 601.1 秒，成功轨迹吞吐 15.97 条／分钟；`peak_rss_mb=7452.4` 是成功 worker 的进程峰值最大值，**不是整机或全部 worker 的总内存峰值**。包装墙钟 291 秒。

全量根包含 365 个文件、88,082,246,321 字节，留在 `artifacts/`。其中 160 个正常 H5 与 5 个 `FAILED_` H5；后者仅为失败证据，未算作训练成功轨迹。未新增 GPU 高频监控，因此不报告利用率稳态结论。

## 七、生成过程与拒绝证据

180 张卡均 attempt=0，独立 `task_success` 与 `ok` 在本批 180／180 相同。生成器因正常拒绝退出 **1**；这不是退出零，最终交付依据身份完整性、失败类型与独立成功字段分别判定。汇总、视频、对比包装退出 **0**。

| 官网编号 | 任务与 seed | 五档结果 | 原因 |
|---|---|---|---|
| 2.4 | ButtonUnmaskSwap 10500 | 五档拒绝 | graph 阶段 |
| 3.2 | VideoRepick 10000 | 五档拒绝 | graph 阶段 |
| 3.2 | VideoRepick 10400 | 五档拒绝 | graph 阶段 |
| 3.2 | VideoRepick 12800 | 五档拒绝 | segment_start 阶段、实际扫掠检查 |

12800 是全量时新增的运行期拒绝：第 0 段、control_step=197，cube_2 与 bystander_0（按钮）中点接触，gap=-0.00013856130198156708 m（约 -0.139 mm），s=0.6875、区间 [0.625,0.75]、depth=3。五档均被同一碰撞守卫拒绝，未修代码、放宽阈值或重试。原始拒绝细节见 [full_run_compact.json](records/full_run_compact.json)，保留的失败 H5／录像路径见 [full_failed_artifacts.json](records/full_failed_artifacts.json)。

## 八、生成后验收与旧轮保护

两轮各 180 个身份均无缺项、重复、未知或基础设施失败。逐母 seed／档位对照见 [full_v1_vs_v2.md](records/full_v1_vs_v2.md)。v1→v2：VideoUnmaskSwap 9300、VideoRepick 11200 各恢复五档；VideoRepick 10000、10400、12800 各新增五档拒绝；ButtonUnmaskSwap 10500 持续拒绝。净变化为成功数 165→160。

`GRADIENT_REVIEW=INFO groups=30 rows=180 failed=20 missing_mother=0 non_monotonic=0`。这里仅检查成功档长度单调性，不是训练梯度一致性。汇总明细见 [full_summary_compact.json](records/full_summary_compact.json)。

30 支六列视频均用 ffprobe 核对：3072 像素宽、30 fps、非空、三任务各十支。主会话已亲眼查看六张位图：5700、9300 的交换段；7700 的按钮开场；11200 的交换段；10500、12800 的失败占位。标题、目标文字、六列画面与红框对齐，无文字截断或重叠；样本路径与指纹见 [full_visual_frames.json](records/full_visual_frames.json)。这只是视觉抽查，不替代碰撞守卫，也不证明机械臂或桌面碰撞安全。

旧根 `artifacts/xhard/xhard-1012-coll/` 的 426 个文件、96,013,180,687 字节及全树只读状态已核对一致，证据见 [old_run_after_full_sizes.json](records/old_run_after_full_sizes.json)。完整 sha256 复核 426 项全部一致、退出 0，`OLD_RUN_INTACT=PASS files=426 mismatches=0`；[判定快照](records/old_run_after_full.json) 与 [逐文件输出](records/old_run_after_full.sha256.log) 均留档。旧文件没有被重写、移动或删除。

## 九、用户决定原话

1. 「同意修订后的 2.95.2 计划，开工继续。有重大口径调整一律停工问我，全量仍在 smoke 后单独报批。」
2. 「参考最新的计划，继续进行。」
3. 「开始全量生成之后是否意味着代码已经不会再修改了？」
4. smoke 结果已呈现后，两次：「你还在等什么，为什么还不开始。」主会话按当前完整计划的阶段 E 启动全量，不要求用户再审同一版本。

## 十、计划外事件与处置

VideoRepick 12800 的运行期碰撞使拒绝数从预扫预计的 15 增至 20；属于计划允许的任务拒绝，保留证据并继续既定批次，没有调整机制、接口、范围或判据。没有基础设施故障、绑定失败、进程池损坏、重试或额外采样。

视频工具以 `ok` 决定失败占位，本批已核实与独立 `task_success` 完全一致；没有因此改动工具。生成、包装只输出新目录；运行代理未修改源码，主会话负责监听、预算和留档。

## 十一、结论与后续边界

当前计划的全量生成、身份对账、汇总、六列视频及两轮比较已完成。160 条成功轨迹可按独立成功字段筛选；20 个拒绝身份与五个失败 H5 保留作证据，不补 seed 或重跑。后续扩大生成、修改判据、处理新碰撞拒绝均需新的明确范围；本次不加入额外任务。

## 十二、归档文件与复现入口

本目录只保存 Git 无法还原的实测记录，没有 bash、yaml、H5、权重或视频拷贝。上述 records 包含压缩后的运行／汇总明细、母清单、两轮对比、视频元数据、位图指纹、失败产物索引、源码冻结证明与旧轮复核证据。

[full_generation.summary.log](records/full_generation.summary.log) 从原始 70,756,099 字节清洗为 40,647 字节：去除 tqdm 中间态，将唯一巨大的 JSON 汇总行替换为明确的计数摘要；全部身份、失败与指标另外保存在 compact JSON，原始日志及完整运行期检查仍留在 `artifacts/`。原始与清洗后均保留一条 `EXIT_CODE=1`，没有改写退出状态。

新产物入口：[汇总](../../../artifacts/xhard/xhard-1012-swapv2/report/summary.md)、[两轮对比](../../../artifacts/xhard/xhard-1012-swapv2/report/v1_vs_v2.md)、[30 支六列视频](../../../artifacts/xhard/xhard-1012-swapv2/report/per_episode_strip/)。完整生成与包装命令分别可从 Beta 启动文档、本文件第三节还原。旧轮哈希复核命令：`timeout 280s sha256sum -c docs/xhard-doc/xhard-1012-swapv2/records/v1_coll_freeze.sha256`。
