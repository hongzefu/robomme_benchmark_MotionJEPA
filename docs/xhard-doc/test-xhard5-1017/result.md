# test 布局 xhard 五档全量生成结果（1017 计划生成侧）

起跑档案见 [launch.md](launch.md)，权威计划是 [`1017-test-xhard5-12per-plan.html`](../../../1017-test-xhard5-12per-plan.html)。时间一律为美国东部时间（2026-10-18）。

## 一句话结论与判定行

624 条 xhard 全部生成成功，0 条耗尽。五组校验全部通过。seed 已纯追加进官方 test metadata 的 14 个文件，并打上 tag `v2-motionmem-eval-test1017-metadata`（commit `943ddf32`，02:18 推到远端），评估分支的子模块已锁定这个 tag。

| 判定行 | 结果 |
|---|---|
| `SMOKE1` | `PASS`：VideoUnmaskSwap ep50，seed 555000，attempt 0 |
| `SMOKE2` | `PASS requested=28 success=28 exhausted=0`，270 s |
| `GEN_FULL` | `PASS requested=624 exhausted=0`（G5-r2 480、G4 48、G3 36、G2 24、G1 36） |
| G5-r2 | `IDENTITY_AUDIT=PASS episodes=480`、`H5_SCHEMA=PASS files=40 steps=36665`、`H5_CONTENT=PASS fails=0`、`H5_COUNTS=PASS tasks=8 episodes=60`、`PLAN_VS_RECORD=PASS rules_run=65 mismatch=0 exempt=5` |
| G4 StopCube | `IDENTITY_AUDIT=PASS episodes=48`、`H5_SCHEMA=PASS files=4 steps=1620`、`H5_CONTENT=PASS`、`H5_COUNTS=PASS`、`PLAN_VS_RECORD=PASS rules_run=4 exempt=4` |
| G3 PickHighlight | `IDENTITY_AUDIT=PASS episodes=36`、`H5_SCHEMA=PASS files=3 steps=2665`、`H5_CONTENT=PASS`、`H5_COUNTS=PASS`、`PLAN_VS_RECORD=PASS rules_run=6 exempt=3` |
| G2 VideoPlaceButton | `IDENTITY_AUDIT=PASS episodes=24`、`H5_SCHEMA=PASS files=2 steps=2477`、`H5_CONTENT=PASS`、`H5_COUNTS=PASS`、`PLAN_VS_RECORD=PASS rules_run=2 exempt=0` |
| G1 | `IDENTITY_AUDIT=PASS episodes=36`、`H5_SCHEMA=PASS files=3 steps=2347`、`H5_CONTENT=PASS`、`H5_COUNTS=PASS tasks=3`、`PLAN_VS_RECORD=PASS rules_run=3 exempt=0` |
| `META_APPEND` | `PASS added_records=624 holes=0` |
| `PROTECTED_APPEND_ONLY` | `PASS files=14 deleted_lines=14 deleted_only_record_count=14 old_records_unchanged=14 env_id_unchanged=14` |
| `TAG` | `v2-motionmem-eval-test1017-metadata sha=943ddf3221e8b20d7369bacd209a3afc1786503b`（tag 对象 `3311edf3`） |

## 生成过程

G5 首轮以 `--workers 32` 起跑（00:31，`SOURCE_HEAD=53c09113` 即 2.154Beta）。约 25 分钟、成功 82 条后，GPU0 进程池崩溃：在飞的 32 个 episode 全部报 `BrokenProcessPool`，产生 31 个 `CRASHED_` 隔离文件。崩溃时 `/proc/pressure/memory` 的 full avg60 为 28%，swap 用到 3.9 G。原因是 aspen 只有 16 核、251 G 内存，而 32 worker 这个口径是按 vail（32 核、377 G）定的；xhard 长 episode 的单 worker 内存在 7～8 G 左右。主会话停掉了 `xh-testx-full`（删前删后各跑一次 `tmux ls`，差集只少这一个会话；停后没有残留进程），改用 `run_full_r2.sh`。r2 与原脚本只差两处：`--workers 16`，以及 G5 的输出目录改为 `full/G5-r2`、8 个任务完整重跑。原 `full/G5/` 目录（82 条成功、31 个 `CRASHED_`）原样保留，不删除，也不参与校验、追加和上传。r2 于 00:53 起跑，同样从 `SOURCE_HEAD=53c09113` 开始，02:17 全部结束，期间 0 次池崩溃。

| 组 | 条数 | 用时 | 峰值 RSS |
|---|---|---|---|
| G5-r2 | 480/480 | 4086 s | 9.5 G |
| G4 | 48/48 | 173 s | 3.8 G |
| G3 | 36/36 | 258 s | 5.9 G |
| G2 | 24/24 | 266 s | 6.9 G |
| G1 | 36/36 | 267 s | 7.1 G |

r2 中共有 226 次任务性失败后换 seed 重试（T10：attempt+1，上限 100）：SwapCollisionError 166 次、DatasetGenerationError 39 次、SceneGenerationError 20 次、FailsafeTimeout 1 次。成功时的 attempt 分布为 attempt 0 有 514 条、1 有 62 条、2 有 25 条、3 有 8 条、4 有 5 条、5 有 3 条、6 有 4 条，7、9、15 各 1 条（统计口径是日志里的 `succeeded … attempt` 行，含冒烟以外的全部五组）。耗尽数为 0，因此不需要补 seed（P8）。

G5-r2 的 `hdf5_files/` 下另有 5 个 `FAILED_VideoRepick_*.h5`，videos 目录下也有若干 `FAILED_*.mp4`。它们是任务性失败时已经开始录制的失败尝试，生成器按设计加上 `FAILED_` 前缀保留，作为失败证据，与 1012 swapv2 的口径相同。它们**不是训练样本，也不在 metadata 中**；metadata 只引用 624 条成功 seed。

## 实施中调整（均经一个对抗验证子代理审查）

1. **worker 32→16，G5 换目录重跑**：`ADJUST_REVIEW=PASS scale=same findings=4`，详见上节。
2. **`PROTECTED_APPEND_ONLY` 的删除行数**：计划写的是 `deleted_lines=28`，预估每个文件删除 `record_count` 行和原末条的 `}`。实测 git 把原末条的 `}` 当作上下文，每个文件只删除 `record_count` 这一行，合计 14 行；用 `git diff -U0 | grep '^-[^-]'` 核对，14 行全部是 `"record_count": 50,`。实际结果比原判据更严：`ADJUST_REVIEW=PASS scale=same findings=0`。
3. **上传计数**：上传目录中 h5 共 629 个，其中独立统计的成功 h5 为 624 个，失败尝试 5 个。产物原样上传，`EXPECT_H5=629`，判定行写作 `h5=629 success=624 failed_attempt=5`：`ADJUST_REVIEW=PASS scale=same findings=2`。
4. **aspen 没有 IPv6 出口**：curl 正常，但 Python 进程解析域名时先拿到 IPv6 地址，每个都要卡到超时。只对上传和拉取 ckpt 的 hf 进程注入 `artifacts/test-xhard/eval-prep/ipv4only/sitecustomize.py`，把地址过滤为 IPv4；不改系统配置，这个文件也不进仓库。

## 长尾（交接后继续）

| 事项 | tmux | 日志 | 完成行 |
|---|---|---|---|
| HF bucket 上传（`HongzeFu/robomme-test-xhard5-12per-1017`，2026-10-19 改为公开；G5 的前缀为 `G5-r2/`） | `xh-testx-upload` | `artifacts/test-xhard/upload/upload.log` | `HF_UPLOAD=PASS objects=1452 bytes=380899594935` |
| GL 纯 CPU 读回校验（job 64268308） | 无 | NFS `logs/testx-hfverify/testx-hfverify_64268308.out` | `HF_VERIFY=PASS objects=1452 sha_match=1452 size_equal=1452 missing=0 extra=0 mismatch=0 checked=1452` |

长尾经过：第 1、2 轮上传因 HongzeFu 私有存储额度满报 403（需开自动充值），停在约 60 G；用户 2026-10-19 裁决「bucket改为公开 上传」，第 3 轮 `run_upload3.sh` 先 `hf buckets settings --public` 再按 BATCH=1 续传，美东 10-19 02:40 前后 `HF_UPLOAD=PASS`。GL 读回首次冒烟（job 64268290）因计算节点 uv managed Python 找不到 CA 证书 `CERTIFICATE_VERIFY_FAILED`，提交时加 `SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt` 后冒烟 64268304 与全量 64268308 均 PASS，未改脚本。

## 归档

本档案只记录判定行与过程，不归档 h5 和视频。产物留在 aspen 的 `artifacts/test-xhard/`：`full/G1..G4`、`full/G5-r2`，以及中止轮 `full/G5`。各组的校验原始输出在 `full/<组>/{audit,check}.log` 与 `check.{json,md}`，生成日志在 `logs/full.log`（中止轮，末行为主会话写入的 `EXIT_CODE=KILLED_BY_MAIN_SESSION…`）和 `logs/full-r2.log`（`FULL_DONE fail=0`、`EXIT_CODE=0`）。
