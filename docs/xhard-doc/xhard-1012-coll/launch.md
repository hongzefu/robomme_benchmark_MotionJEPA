# xhard-1012-coll 全量派生：launch（第一段，起跑前写）

档案名 `xhard-1012-coll`，按 AGENTS.md 第 13 条留档。计划为 [`1012-swap-collision-plan.html`](../../../1012-swap-collision-plan.html)（方案 X′ 小节与阶段 E、4.1/4.2）；跑完后的实测写在同目录 `result.md`。

## ① 一句话

对三个交换任务（2.3 VideoUnmaskSwap、2.4 ButtonUnmaskSwap、3.2 VideoRepick）各 10 个官方 train 母 seed，带运行期碰撞检测派生 xhard12/14/16/18/20 五档，另按同 seed 重生成母档，共 180 张卡，统计成功率并出六列横排视频。

## ② 版本与代码状态

- 代码版本：本文件所在的 Beta 提交（subject `2.93Beta …`），起跑前 porcelain 必须为空（`docs/subagent-stats` 除外）。
- 本轮相关链路：2.80～2.82 碰撞规划、运行期复核与生成器证据；2.89 方案 X（段起点复核移到 `_before_control_step`）；2.92 方案 X′（`swap_plan.py::parent_start_q`，期望端点四元数先重放父类 `statechange.py::swap_flat_two_lane` 段起点的 float32 归一化，四字段仍 `np.array_equal`）。
- 受保护目录 `src/robomme/` 零 diff（P1）；ManiSkill 钉 `07be6fbc66350ddca200abfb0a11b692f078f7fd` 不变。

## ③ 起跑前闸门（同一 HEAD `bbff9f0b`，2.92）

| 步 | 结果 | 日志 |
|---|---|---|
| Y1 首探针 VideoUnmaskSwap seed5700 xhard12 | 1 passed，15.23 s，EXIT_CODE=0；该轮 JSON 中 156 条 `endpoint_match: true`、0 条 false。`XHARD_SEG_START_ALIGN=PASS mismatches=0` | `artifacts/logs/xh-coll-y1-probe-1012.log`，JSON 根 `artifacts/tests/swap-timing/run-1791843276870836592/` |
| Y2 剩余 GPU 契约 | 14 passed，66.71 s，EXIT_CODE=0 | `artifacts/logs/xh-coll-y2-contract-1012.log` |
| Y3 D0 故障送达 | `XHARD_FATAL_CATCH=PASS tasks=3 hang=0`，123.19 s，EXIT_CODE=0 | `artifacts/logs/xh-coll-y3-d0-1012.log` |
| Y4 正常 smoke（rank0 三任务各一张 xhard20，GPU0 单 worker） | 3/3 成功，EXIT_CODE=0，总 316.7 s；端点 11+12+15=38 段全部逐位一致、0 拒绝；子步检测 before/after 各 2755/3005/3755 次 | `artifacts/logs/xh-coll-y4-smoke-1012.log`，产物 `artifacts/xhard/xhard-1012-coll/timing-smoke/` |

Smoke 单卡 wall：VideoUnmaskSwap 105.5 s、ButtonUnmaskSwap 156.5 s、VideoRepick 50.5 s（单 worker、vail）；xhard-1011 无检测时为 56/58/91 s（aspen、多 worker），机器与并发不同，不作严格耗时比。H5 每卡 589 / 605 / 927 MB，三卡含视频与结果文件共 2.17 GB。

规模估算：按 smoke 每卡均值约 0.72 GB × 180 × 1.3 ≈ 170 GB，`/data` 可用 6.4 T（低于 10% 阈值）；耗时按 smoke 单卡合计 311 s 对 1011 的 205 s 约 1.5 倍，套 4.1 基线 9 260 卡·秒得约 14 000 卡·秒，32 worker 理想约 8 分钟，单卡 32 进程争用下预计 15～40 分钟（低于 1 小时阈值）。内存 377 GB（可用约 328 GB），smoke 单卡峰值 RSS 4.9 GB。用户本轮「然后做全量的生成」作为对本批 180 卡的决定（P5，计划 D11）。

## ④ 启动与配置还原

运行位置：sled-vail 本机主检出 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，GPU0（起跑前 1286 MiB / 0～13%），tmux 会话 `xh-coll-full-1012`，由运行型子代理 R1 启动、主会话 Monitor。

```bash
tmux new-session -d -s xh-coll-full-1012 "set -o pipefail; cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006; PYTHONUNBUFFERED=1 UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --env VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick --difficulty xhard12,xhard14,xhard16,xhard18,xhard20 --mother-manifest artifacts/xhard/xhard-1012-coll/mother_seeds_all.json --with-mother --gpus 0 --workers 32 --output-dir artifacts/xhard/xhard-1012-coll/full 2>&1 | tee artifacts/logs/xh-coll-full-1012.log; echo \"EXIT_CODE=\$?\" >> artifacts/logs/xh-coll-full-1012.log"
```

| 项 | 值 | 说明 |
|---|---|---|
| `--env` | 三个交换任务 | 官网顺序 2.3、2.4、3.2 |
| `--difficulty` | `xhard12,xhard14,xhard16,xhard18,xhard20` | 150 张 xhard 卡 |
| `--mother-manifest` | `artifacts/xhard/xhard-1012-coll/mother_seeds_all.json`（副本 `records/mother_seeds_all.json`） | `mother_seeds --all --limit 10 --no-verify`：`XHARD_MOTHER_ALL=PASS tasks=3 seeds=30 limit=10`、`XHARD_MOTHER_NO_FAILRECOVER=PASS seeds=30 min_episode=6`、`XHARD_MOTHER_OFFICIAL=PASS seeds=30 max_episode=43` |
| `--with-mother` | 开 | 30 张母卡 |
| `--gpus` / `--workers` | `0` / `32` | K13；vail 32 核 |
| `--output-dir` | `artifacts/xhard/xhard-1012-coll/full` | 起跑前不存在 |
| attempt | 固定 0 | 失败不换 seed、不重试（P2） |

母 seed：VideoUnmaskSwap 5700…9300（步长 400）；ButtonUnmaskSwap 7700…11300；VideoRepick 9600、10000、10400、10800、11200、11602、12000、12400、12800、13200。

## ⑤ 盯盘与停止条件

Monitor 过滤 `succeeded with seed|EXIT_CODE=|SwapCollisionError|SwapBindingError|failed|进程池已损坏|ERROR:|Traceback|BrokenProcessPool|svulkan2|out of memory|NO RECORD`（`screw plan failed` 为规划器内部重试输出，smoke 与 D0 均出现且卡成功）。停下交用户：任一任务 `SwapBindingError` 超过该任务卡数 10%、进程池损坏、墙钟超过 1 小时、GPU0 被他人占满。基础设施故障卡移 `_quarantine/`，不自动重跑。

## ⑥ 本轮 tmux 会话清单

`xh-coll-y123-1012`、`xh-coll-y4-smoke-1012`（均已自行退出）、`xh-coll-full-1012`。不在清单内的会话一律不动。
