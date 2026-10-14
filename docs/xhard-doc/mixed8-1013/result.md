# 八档循环本机阶段结果

## 一、一句话结论与指标

本机代码实现、规则填充与首次正式校验已执行完；数据未满足完整交付判据。第一批单条通过，第二批 128 个身份中 127 成功、1 耗尽；首档校验期望 100 个样本、实有 99 个，现有样本未发现结构、内容或可数语义不符。四条总体判定均因同一个缺失身份而失败，不能写成全量通过。AWS 尚未启动。

```text
LIGHT_TESTS=PASS failed=4 new_failures=0 passed=679
PROTECTED=PASS base=94c6a90b312c35ebf1a47940cd4d8159523212ce tip=3303ff3683f4697f06bf24c214fe3e4b1edb420a
SMOKE1=PASS gym_id=VideoUnmaskSwapXHard difficulty=xhard12 timestep=525 seed=5300 attempt=0 task_success=1 elapsed_s=42.2
SMOKE2=FAIL requested=128 success=127 exhausted=1 z=33 xy=14 elapsed_s=501.0
IDENTITY_AUDIT=FAIL episodes=128 missing=3 dup=0 unknown=0 mismatch=1
H5_SCHEMA=FAIL files=99 steps=69222 missing=1 extra=0 dtype_shape=0
H5_CONTENT=FAIL files=99 fails=1
H5_COUNTS=FAIL tasks=16 episodes=8 per_tier_ok=0
PLAN_VS_RECORD=FAIL files=52 rules_expected=80 rules_run=79 mismatch=1 exempt=12
WORKER_EXIT=PASS known_workers=33 remaining=[]
```

`IDENTITY_AUDIT missing=3` 表示同一身份缺成功记录、metadata、H5 三处，并非缺三个 episode；`H5_COUNTS episodes=8` 是每任务期望数。语义行的 `files=52` 是冻结的 xhard 样本期望，实际可读为 51 个；80 项中实际真数 67 项、获批豁免 12 项、缺失未执行 1 项。99 个实有样本的个体失败列表为空，完整范围仍 FAIL。

## 二、版本与代码状态

生成时完整 HEAD 为 `76572b215c9cc7ccbf07c725297dd0ef3403b799`，起跑工作区干净，两次冒烟期间 HEAD 未变；见 [起跑快照](records/launch-identity.json)与两份清洗日志的 `SOURCE_HEAD`。正式校验 HEAD 为 `3303ff3683f4697f06bf24c214fe3e4b1edb420a`，包含获批 W5 规则和豁免，起跑工作区同样干净，运行时未改变源码或依赖。

W1–W4、W6、W5 均在独立工作树修改，经过固定版本独立审查，以 `--no-ff` 保留全部子提交合入并推送。最新合并为 `2.124`；W5 合并后核心短测 679 通过、精确四个旧失败、2 跳过、137 排除、19.52 秒、退出 1。四个允许失败身份与命令完整列在 [实施记录](implementation.md)，没有新增失败。

`src/robomme/`、`src/robomme_xhard/base.py`、`configs.py`、`envs/` 相对开工基线零差异；`pyproject.toml`、`uv.lock` 未改。源码复核命令为：

```bash
git diff --quiet 94c6a90b312c35ebf1a47940cd4d8159523212ce 3303ff3683f4697f06bf24c214fe3e4b1edb420a -- src/robomme/ src/robomme_xhard/base.py src/robomme_xhard/configs.py src/robomme_xhard/envs/
```

## 三、启动与配置还原

完整命令、环境变量覆盖、默认参数、硬件与启动器 SHA256 见 [launch.md](launch.md)。两批均用 `train` 公式 seed、八档循环、GPU0、最大 100 次 attempt，第一批 1 worker，第二批 32 worker；限线程开启、每进程最多 8 个作业、`affinity=none`。第二批 detached tmux 名为 `xh-mixed8-smoke2`，正常以程序退出码 1 结束，精确会话随后不存在，其他七个原有会话保留；只关闭了本轮前台日志监听。

首次正式校验命令如下，完整输出在 [check.log](records/check.log)，退出 1：

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv uv run --no-sync python -m robomme_xhard.tools.check_mixed_h5 check \
  --output-dir artifacts/mixed8/smoke2 --golden-dir src/robomme_xhard/tools/golden_schema \
  --cycle easy,medium,hard,xhard12,xhard14,xhard16,xhard18,xhard20 --episodes 8 --workers 32 \
  --out-json artifacts/mixed8/smoke2/check.json --out-md artifacts/mixed8/smoke2/check.md
```

## 四、数据与划分口径

原计划 16 任务各 ep0–7，共 128 个身份，不从母清单取 seed；任务内难度按有效循环，缺档剔除，`env_code` 原规范序保持。失败按批准的 `attempt+1` 公式推进，耗尽项没有追加 seed、补跑或替换。唯一耗尽为 `VideoPlaceOrder/ep3/xhard12`，尝试 seed `11300`、`11301`、`11302` 后按连续三次非任务失败停止。

正式首档样本仍固定为每任务每有效档第一条。VideoPlaceOrder ep7/xhard12 成功只用于 W5 核实规则，未替代 ep3；因此正式首档样本 99/100。Golden 从只读原版副本每任务 `episode_0` 导出，revision 和排除字段见代码内 16 份 JSON；未扩白名单，未做原版全文件 SHA256 复核。

## 五、各任务生成结果与尝试分布

| 官网编号 | 任务 | 成功／期望 | 耗尽 |
|---|---|---:|---:|
| 1.1 | BinFill | 8/8 | 0 |
| 1.2 | PickXtimes | 8/8 | 0 |
| 1.3 | SwingXtimes | 8/8 | 0 |
| 1.4 | StopCube | 8/8 | 0 |
| 2.1 | VideoUnmask | 8/8 | 0 |
| 2.2 | ButtonUnmask | 8/8 | 0 |
| 2.3 | VideoUnmaskSwap | 8/8 | 0 |
| 2.4 | ButtonUnmaskSwap | 8/8 | 0 |
| 3.1 | PickHighlight | 8/8 | 0 |
| 3.2 | VideoRepick | 8/8 | 0 |
| 3.3 | VideoPlaceButton | 8/8 | 0 |
| 3.4 | VideoPlaceOrder | 7/8 | 1 |
| 4.1 | MoveCube | 8/8 | 0 |
| 4.2 | InsertPeg | 8/8 | 0 |
| 4.3 | PatternLock | 8/8 | 0 |
| 4.4 | RouteStick | 8/8 | 0 |

总共 173 条 attempt 记录：127 成功记录、34 条任务性失败、12 条代码异常，基础设施失败记录为 0。完整 100 个任务档组合见 [逐档尝试表](records/attempts-per-tier.md)，逐身份尝试列表和两种均值在 [attempts-per-tier.json](records/attempts-per-tier.json)，按官网任务顺序及档顺序排列。达到计划 G4 报告阈值的组合如下：

| 任务／档 | 实际平均尝试 | 汇总平均尝试 | 说明 |
|---|---:|---:|---|
| VideoRepick/xhard12 | 10.00 | 10.00 | 第 10 次成功，attempt=9 |
| VideoRepick/xhard16 | 8.00 | 8.00 | 第 8 次成功，attempt=7 |
| VideoPlaceOrder/xhard12 | 2.50 | 51.00 | 两身份，ep3 三次耗尽、ep7 两次成功；耗尽折算 100 |

“汇总尝试”沿用计划 G4 的耗尽计 100 口径，不代表该失败身份实际执行了 100 次。成功和耗尽都保留原记录，不挑成功重跑。

## 六、硬件、耗时与体量

本机 sled-vail、32 核、RTX 6000 Ada GPU0；NVMe 输出，依赖版本见启动档案。第一批生成 42.2 秒，第二批 501.0 秒；这两个生成阶段单卡墙钟合计约 0.151 GPU·h，不是 GPU 实际利用率测量。未在 vail 跑测速阶梯，也没有据此宣布 32 worker 为正式最优。

第二批产物体量为 59,571,863,081 字节，约 59.6 GB／55.5 GiB；127 个 H5，另有视频、日志与结果。失败产物 27 个、250,769,346 字节，占约 0.42%，低于计划 10% 的报告阈值。原产物全部保留于 `artifacts/mixed8/`。

以这 127 个成功样本的整批体量作直线参考，6400 条约为 3.0 TB，明显高于原计划 1.2–1.6 TB 估计。该数包含本批失败产物，且本批 FailRecover 占比和全量不同，只是容量参考；AWS 阶段还要以自己的实测核定，不能把原 2 TB 最小磁盘判据理解为已证足够。

## 七、运行行为与唯一缺失原因

唯一耗尽的 traceback 先出现拥挤场景采样拒绝，随后 `SceneGenerationError` 被当模块调用或用于 `except`，引出 `TypeError`。以下三文件的模块导入区先导入异常类，再 `from .utils import *`；通配导入把同名异常类覆盖为模块：

| 官网编号 | 文件与锚点 | 本批影响 |
|---|---|---|
| 1.3 | `src/robomme/robomme_env/SwingXtimes.py` 模块导入区、`_load_scene` | 1 条代码异常后重试成功 |
| 3.2 | `src/robomme/robomme_env/VideoRepick.py` 模块导入区、`_load_scene` | 部分场景拒绝被包装为代码异常，最终均成功 |
| 3.4 | `src/robomme/robomme_env/VideoPlaceOrder.py` 模块导入区、`_load_scene` | ep3 连续三次代码异常耗尽 |

除原 traceback，CPU 只读导入诊断也确认三处绑定的 `type` 为 `module`，见 [exception-bindings.json](records/exception-bindings.json)。这是冻结源码中的既有问题；本轮没有通过 monkeypatch、子类覆盖或修改源文件绕过它。若修复，候选是将显式异常类导入放到通配导入之后，须依 P1／计划 R1 单独取得这三处修改授权；当前未实施，也未补生成缺失样本。

## 八、首次正式校验

逐文件与逐项原始结果在 [check.json](records/check.json)，可读失败导读在 [check.md](records/check.md)。99 个实有样本合计 69,222 个 timestep，个体 `schema_errors`、`content_errors` 与可数语义 mismatch 列表均为空；所有总体失败均追溯到 `VideoPlaceOrder/ep3` 缺失。

结构判定没有把不可读或缺失文件当通过；语义期望来自冻结循环和 80 项集合，不随实际读到 51 个 xhard 文件缩成 79 项。身份对账没有重复、未知身份或其余 seed／档／FailRecover 不符。z=33、xy=14 的实际落点与计划相同。

## 九、用户决策记录

按时间顺序保留本轮关键原话：

1. 「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1013-mixed8-400ep-plan.html 开始实现 有问题问用户」。
2. W4 第二轮仍失败后的裁决：「允许最小修复并增量重审（推荐）」。
3. 具名豁免清单呈现后的裁决：「批准这三项豁免并继续校验（推荐）」。

第三条仅批准 `StopCube.stop_k` 四个档样本、`PickHighlight.spawn` 三个档样本、`PatternLock.grid` 五个档样本，共 12 项；路径长度、动作数量和缺失身份均未豁免。原范围与历史口径原话在计划 K1–K18，不将本次批准解释为冻结源码修复或追加生成授权。

## 十、计划外事件与实施中调整

两个同等规模调整均先通过单一独立对抗验证：停档时仅调用 `shutdown` 不能终止运行 worker，补齐现有停档支路的终止与等待；真实路径边界需要倍率，补 `knob_affine` 线性表达式。两次均 `ADJUST_REVIEW=PASS scale=same findings=0`，未叠加守卫、回退、开关或依赖；详细旧→新与文件归属已同步计划。

独立审查另发现并修复默认池隔离竞态、结构与语义假通过、信号清理与截断 JSONL 证据问题；W4 第二轮尾部信号问题按 G1 停下来取得用户批准后才继续。旧提交反例和修复验证均保留，未改验收阈值。

校验原估约一分钟，实际 `CHECK_WALL_S=490`，超过五分钟。它按原短测估计以前台命令启动，没有伪称 detached tmux；运行期间主会话持续观察、起跑提交 `3303ff3683f4697f06bf24c214fe3e4b1edb420a` 与完整命令在原日志中，运行期间不改源码，实际输出与退出状态全部保存。未因超时截短样本或重启校验，也未把事后留档提交当启动版本。该耗时估计偏差应供后续同规模校验采用长任务纪律。

交付前已将计划机制图 1 渲染为位图并目视复核：箭头没有交叉或穿框、文字没有溢出或缺字、图例颜色一致，无须改原 SVG。首次提取时额外插入了原图已存在的字体属性，临时渲染被 XML 解析器拒绝；去掉该重复插入后原 SVG 渲染通过，未改计划图源码或正式依赖。

仍未验证 AWS 的渲染、监控开销、内存探针、稳态吞吐、最优 worker、全量及跨机器数值差异；未与 MotionJEPA 读取器对拍。十二项豁免不保证对应物理数量，只说明用户接受当前观察器范围。

## 十一、当前结论与下一步

代码实现与本机阶段按授权终点执行完，当前数据与四项完整交付判据为 FAIL。没有本轮仍运行的 GPU worker、tmux 生成会话或校验进程；33 个已知 worker PID 是累计值，包含进程回收替换，并非宣称 33 个同时运行。保持原日志、失败与成功产物，等待用户启动 AWS；不自行进入环境 C、测速或全量。

本轮四个临时工作树均在工作区干净、全部子提交已整合之后通过应用工具作可恢复归档；主检出、既有其他工作树及全部生成产物保留。`WORKTREE_ARCHIVE=PASS own=4 remaining_own_active=0`，应用附件已显示四个 `archived_worktree`，Git 工作树清单回到原有集合。

AWS 起跑前宜先裁决三处冻结源码的异常名遮盖问题，并用实际体量确定存储余量。任何修复或追加生成都须新的明确授权；本批结果不被事后改成完整通过。

## 十二、归档文件

`records/` 只归档 Git 无法还原的现场证据：起跑身份快照、两批摘要与单条验证、批次验证／失败 traceback／异常绑定诊断／体量、身份对账、清洗日志、正式 `check.json`／`check.md`／`check.log`、完整逐档尝试分布。原 H5、视频与启动器保留在 `artifacts/`，不进 Git；配置由启动档案加源码提交还原，没有脚本或 YAML 拷贝。

清洗核对 `LOG_CLEAN=PASS`：第一批 `EXIT_CODE=0` 一条，第二批 `EXIT_CODE=1` 一条，数量和值与原日志一致；校验原日志为 `CHECK_WALL_S=490`、`EXIT_CODE=1`。源码、结果、失败与用户裁决各自保留原始身份，不用 aggregate PASS 代替独立判定。

---

# AWS 环境 C 阶段结果（2026-10-14 追加）

以上为 vail 本机阶段结果，原文不改。本节记录 AWS p4de（环境 C）上的接入、测速与全量；起跑口径见 [launch.md](launch.md) 末尾「AWS 环境 C」一节，起跑锚点 `2.131Beta`（`0e8d249acd87c4d09a2a030d643e7f4fb93a28bc`）。

## 一、一句话结论与指标

环境接入、smoke 一、内存探针与三档测速全部通过，选定 W\*=64；全量按计划起跑，约 56 分钟、完成 718/6400 条（BinFill 307、PickXtimes 382、SwingXtimes 29）时**按用户指令中止**，产物经用户指令删除。全量未完成，第二次校验、身份对账、跨机器对拍均未执行。

```text
ENV_C=PASS host=ip-10-242-11-177 gpus=8 disk_free_tb=3.14 sha=ea7cb1bbd85873a45bc2b12cbfd45e87500036cb
SMOKE1=PASS gym_id=VideoUnmaskSwapXHard difficulty=xhard12 timestep=525 seed=5300 attempt=0 task_success=1 elapsed_s=96.4
MEM_PROBE=PASS peak_rss_gb=8.28681640625 peak_vram_gb=0.7874755859375 mem_avail_gb=1067.5172424316406
CALIB=PASS probe_rss_gb=8.28681640625 probe_vram_gb=0.7874755859375 cells_run=3 skipped=none best_workers=64 crashed_at=none
GEN_FULL=ABORTED requested=6400 success=718 failed_attempts=106 exhausted=0 reason=user_stop
H5_SCHEMA／H5_CONTENT／H5_COUNTS／PLAN_VS_RECORD／IDENTITY_AUDIT（第二次）=未执行
XMACHINE_JOINT_DIFF=未执行（vail smoke 二样本未传入本机，且全量中止）
```

## 二、版本与代码状态

接入与测速在 `ea7cb1bb`（2.130）上运行，工作区干净；全量在 `2.131Beta` 上运行，启动器打印 `SOURCE_HEAD=0e8d249a… DIRTY=0`。全程未改任何代码、依赖或配置；`src/robomme/` 工作区零 diff。

## 三、测速

| 档 | workers | 卡序 | 成功／请求 | 稳态吞吐（条/分） |
|---|---:|---|---:|---:|
| P8 探针 | 8 | 0 | 16/16 | — |
| L32 | 32 | 0,4,1,5 | 384/384 | 17.07 |
| L64 | 64 | 0,1,4,5,2,3,6,7 | 384/384 | 17.80 |
| L96 | 96 | 0,1,4,5,2,3,6,7 | 384/384 | 17.03 |

三档吞吐持平：CPU 约 75% 空闲、GPU 利用率 5–12%，单条 wall_s 随 worker 数近乎线性增长（L32 100.8 s → L64 186.9 s）。L96 起跑阶段观察到 95 个 D 状态进程全为 nvidia-smi 卡驱动锁，负载下单次 `nvidia-smi` 8.9–13.5 秒；来源与经用户批准终止的两个外部进程见 launch.md。smoke 二唯一耗尽的 VideoPlaceOrder ep3/xhard12 在三档测速中均成功（W7 修复后）。证据：`records/aws-calibration.md`、`records/aws-calib-*-cell-summary.json`、`records/aws-calib.summary.log`。

## 四、全量运行与中止

- 02:59:40 UTC 起跑 tmux `xh-mixed8-full-1014`；约 03:55 UTC 用户原话「停止现在的生成」，主会话 `tmux kill-session -t '=xh-mixed8-full-1014'`，删前删后 `tmux ls` 差集恰为该会话，其余六个既有会话不动；随后核对本仓库生成进程为 0、8 卡显存归零。强杀不写 `EXIT_CODE=`，原日志无该行（清洗后同为 0 行）。
- 中止时：结果记录 824 条、成功 718、任务性失败 attempt 106、代码类失败 0、无耗尽；成功条平均 994.9 timestep（作业按任务顺序派发，前段恰为最长的 BinFill／PickXtimes，与 vail 首档样本该两任务均值 1072／1020 一致，不改变全量约 2.93–2.95 TB 的体量估计）；吞吐约 12.8 条/分（718 条／56 分，含启动）。
- `hdf5_files/` 762 个无前缀 H5（478,108,183,768 字节），其中 44 个无成功记录，是强杀时在途的半截文件；`videos/` 954 个（17,533,166,177 字节）。统计见 `records/aws-full-abort-stats.json`。
- 用户原话「这一部分产物全部删除。测速的产物也可以删除只保留文件和所有小文件运行的记录。然后现在归党。」：主会话先把 `run_parameters.json`、`episode_results.jsonl`（gzip）、清洗日志归入 `records/aws-full-*`，再按显式路径 `rm -rf` 删除 `artifacts/mixed8/full/hdf5_files` 与 `videos`（删前 `ls -ld` 核对为实体目录、非 symlink），`/scratch` 空闲回到约 3.4 TiB。测速各档的 H5 与视频已在每档结束时由测速脚本删除，剩余约 89 MB 均为运行记录，按用户要求保留；smoke 一产物（342 MB）未在指令范围内，保留。全量清洗日志额外滤掉刷屏行 `screw plan failed`，718 行 `succeeded with seed` 原样保留。

## 五、用户决策记录

1. 起跑指令与本轮改口径原话见 launch.md「AWS 环境 C」一节第 1 条。
2. 「/scratch 可用空间从 2.9T 涨到 3.4T（占用率 51%），超过了你要的 3.2T。完成后可开始全量。」
3. 「不用用户在再等用户的审批了直接开始全量。」
4. 「VSCode这个可以删除。然后9月13号这个也可以删除」「其他的你可以自己判断。」
5. 「停止现在的生成」
6. 「这一部分产物全部删除。测速的产物也可以删除只保留文件和所有小文件运行的记录。然后现在归党。」

## 六、计划外事件

- 接入时 `/scratch` 仅 3.14 TB，低于用户 3.2 TB；用户清理后 3.73 TB。
- 测速发现 nvidia-smi 驱动锁争用；提出的 PATH 垫片方案用户未作答，全量未采用。
- 全量按用户指令中止并删除产物，计划 R-6 的 GEN_FULL 与 R-7 第二次校验未完成。

## 七、当前状态与下一步

本机无本轮运行中的 tmux 会话或进程；保留 `artifacts/mixed8/{smoke1,calib}` 与 `full/` 下的两个小记录文件、`artifacts/logs/mixed8-{smoke1,calib,full}.log`、两个启动器。若重启全量，需新的明确指令；`artifacts/mixed8/full` 目录仍存在（只含小记录），按 R12 新一轮须换用新的输出目录名。
