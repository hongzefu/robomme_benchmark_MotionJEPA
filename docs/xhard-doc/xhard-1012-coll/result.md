# xhard-1012-coll 全量派生：result（第二段，跑完后写）

## ① 一句话结论与指标速览

180 张卡全部跑完（612.9 s，GPU0、32 worker）：**165 成功、15 张被碰撞检测按设计剔除、其他失败 0**；30 个母档全部成功；三个任务五档成功率均为 **9/10**。方案 X′ 下实际执行的 1139 个交换段端点**全部逐位一致**（0 误报），子步检测共 570 850 次。

`XHARD_FULL_DERIVE=DONE cards=180 ok=165 coll=15 other=0 unknown=0`
`EPISODE_STRIP_VIDEO=PASS videos=30 columns=180 missing=0`
`DIFFICULTY_LABEL=PASS files=165`、`XHARD_RECORD_NONEMPTY=PASS files=165`、`GRADIENT_REVIEW=INFO groups=30 rows=180 failed=15 missing_mother=0 non_monotonic=0`

## ② 任务 × 档位成功率（官网顺序）

| 编号 | 任务 | 母档 | xhard12 | xhard14 | xhard16 | xhard18 | xhard20 |
|---|---|---|---|---|---|---|---|
| 2.3 | VideoUnmaskSwap | 10/10 | 9/10 | 9/10 | 9/10 | 9/10 | 9/10 |
| 2.4 | ButtonUnmaskSwap | 10/10 | 9/10 | 9/10 | 9/10 | 9/10 | 9/10 |
| 3.2 | VideoRepick | 10/10 | 9/10 | 9/10 | 9/10 | 9/10 | 9/10 |

成功卡的 `task_success` 全为 1（`ok` 与 `task_success` 不一致的卡数为 0）。

## ③ 15 张剔除卡（每个任务各 1 个母 seed，五档连带）

| 任务 | 母 seed / episode | 错误类型 × 阶段 | 证据 |
|---|---|---|---|
| VideoUnmaskSwap | 9300 / ep43 | `SwapCollisionError` × sweep（规划期） | 第 0 段 `bin_1`↔`bin_2` 中点判定接触，`gap_m=-0.00170`，`s=0.5` |
| ButtonUnmaskSwap | 10500 / ep35 | `SwapCollisionError` × sweep（规划期） | 第 0 段 `bin_0`↔`bin_2` 接触，`gap_m=-0.00044`，`s=0.25`，二分深度 1 |
| VideoRepick | 11200 / ep22 | `SwapBindingError` × segment_start（运行期，check=binding） | 控制步 253、第 1 段：发起者 0 计划搭档 2，实际位置最近邻为 1，距离 0.16989 m 对 0.17144 m（差 1.5 mm） |

五档是同 seed 前缀关系（K11），因此第 0/1 段即被拒的母 seed 五档全部失败，各任务剔除率 5/50 = 10%。VideoRepick 那张是最近邻绑定检查，不是端点四元数问题：物体在真实物理里的位置相对规划有毫米级偏移，导致最近邻交换搭档改变，按设计判失败、不重试。launch.md ⑤ 的停止阈值是「超过 10%」，实际恰为 10%（5/50），未触发停止。

## ④ 长度（成功卡中位）

| 任务 | 母档 timestep / 窗 | xhard12 | xhard14 | xhard16 | xhard18 | xhard20 |
|---|---|---|---|---|---|---|
| VideoUnmaskSwap | 431.5 / 24 | 525 / 30 | 581 / 33 | 679 / 39 | 779 / 46 | 876 / 52 |
| ButtonUnmaskSwap | 459 / 27 | 549 / 33 | 654 / 39 | 718 / 43 | 820 / 50 | 917 / 56 |
| VideoRepick | 743.5 / 43 | 878 / 51 | 984 / 58 | 1144 / 68 | 1305 / 78 | 1357 / 82 |

净置换恒等（D1，成功 xhard 卡）：VideoUnmaskSwap xhard12 8/9，其余档 0/9；ButtonUnmaskSwap xhard12 9/9、xhard16 8/9、xhard20 8/9，xhard14/18 0/9；VideoRepick 各档 0/9。

## ⑤ 硬件、耗时与产物

sled-vail GPU0（RTX 6000 Ada），32 worker，墙钟 612.9 s，吞吐 16.15 卡/分钟，单卡 wall 中位 99.0 s（最大 232.6 s），峰值 RSS 7.49 GB。产物 `artifacts/xhard/xhard-1012-coll/full/` 共 93.4 GB；六列视频 30 支在 `artifacts/xhard/xhard-1012-coll/report/per_episode_strip/`（284 MB），汇总 `artifacts/xhard/xhard-1012-coll/report/summary.{md,json}`。生成器以 EXIT_CODE=1 退出，原因是 15 张卡未成功（`exhausted_count=15`）；日志无 Traceback、进程池损坏或 OOM，无 `_quarantine/`。

目视复核：抽取 `3.2_VideoRepick_ep22_seed11200.mp4` 第 5 秒帧，母档列正常，五个失败列灰底并标「失败：SwapBindingError」，中文正常渲染。

## ⑥ 用户决策记录

1. 「没听懂什么意思 为什么会出现 为什么有4e-9这种小的差距」→ 解释为父类段起点的 float32 归一化。
2. 「比较前先对缓存做一遍和父类完全相同的 float32 归一化，然后仍然逐位比较。 同意 继续做」「然后做全量的生成」→ 2.91 完整修订方案 X′ 与 D11。
3. 「开工」→ 2.92 合并 T2，Y1–Y5 依次执行。

## ⑦ 计划外事件

- 生成器对任何未成功卡都返回退出码 1，不代表基础设施故障；本档以 run_summary 与逐卡结果为准。
- 全量日志 74 MB，主要是末尾整份 JSON 汇总行；清洗时去掉超过 4000 字符的行（逐卡数据另由 `records/cards_digest.json` 与 artifacts 原件保存，sha256 见 `records/artifacts_manifest.json`），清洗后 165 行成功、15 行失败、`EXIT_CODE=1` 均保留。
- 规划器内部 `screw plan failed` 行在 ButtonUnmaskSwap 出现多次，对应卡均成功。

## ⑧ 结论与下一步

带运行期碰撞检测的三交换任务 xhard 全量数据已生成，成功率 165/180，被剔除的 15 张均有判据证据。方案 X′ 在 1139 段上零误报。下一步由用户决定：是否接受 3 个被剔除母 seed 的缺口，或另议替换 seed 的口径（P2 目前规定失败不换 seed）。

## ⑨ 归档文件清单（records/）

- `mother_seeds_all.json`：母 seed 清单副本（sha256 56a0381b…）
- `summary.md`：summarize 工具输出的逐卡与分组表
- `cards_digest.json`：180 张卡的摘要（不含逐子步记录）
- `artifacts_manifest.json`：大文件字节数与 sha256
- `logs/*.summary.log`：Y1、Y2、Y3、Y4 与全量的清洗日志
