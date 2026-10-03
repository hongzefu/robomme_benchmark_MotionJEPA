> **用途与顺序**：本方案接在根目录 [V8 计划](1001-newtask-v8-xhard-gradient-plan.md)全部完成之后，规划在 Great Lakes 上评估 SimpleMemVLA 与 MME-VLA。本轮只新增这份方案，不提交占位作业、不启动评估、不修改原 V8 计划或在途实现。原计划中的 xhard0 两路线评估仍属于原计划，本方案不接管。
>
> **用户原话，按时间顺序**：①「把方案写在根目录，在V8 Plan Markdown之后，开始两个模型的 evaluation 在 Great Lakes 上进行。」②「这是 V8 Plan Markdown 结束之后开始进行。」③「然后告诉我预估的时间，如果我用十个卡去并行的话。」④（2026-10-02，问口径）「是所有的已经生成过验证过的eisde都要evaluate吗?注意我说的是XHARD1234」⑤（同日，定口径，语音转写原样保留）「修改计划凭X号的12345。Xhard0不评」——即只评 xhard1～xhard5，xhard0 不评。⑥（同日）「这次评估会保留所有视频吗?需要保留所有视频如果没有保留的话。」⑦（同日，交 Codex 审计 `AUDIT_BASE=d7a15870` 七条 P2 意见后）「参考以上Codex的审计意见对于计划进行修改。」⑧（同日，改计划途中两条）「一千600步到了就timeout。」「直接计为timeout」「注意我说的一千600步是指执行步数不包括Demo」⑨（同日）「MME资产的这个锁你要把它锁上。simpleMVRA的这个1600步也要写上。reset额度可以放开到十倍」「如果有问题可以放开到石碑。还有什么没有定下来我需要开跑之后用户去睡觉一直跑到美国东部时间早上十二点。」（语音转写：simpleMVRA 即 SimpleMemVLA，石碑即十倍）⑩（同日 03:13 EDT 后，AskUserQuestion 四问的答复）开工授权：「不开工只审核计划」；中午 12 点未跑完：「继续跑到完成」；tokenizer 可信 SHA256 来源：「对 GCS 官方对象的校验和」；第 1600 步恰好成功：「记成功」。
>
> **规划锚点**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV8`，读取时 HEAD 为 `ae5b85762de69fbdba0728b4f333409a3047d2dd`（12.298）。这是规划依据，不是最终评估版本；实施时记录 V8 收尾提交、评估适配提交、两个 gitlink 的完整 SHA 与权重清单。提交编号沿用仓库 `12.<小版本>`，提交前重新核对。当前 `third_party/SimpleMemVLA` 有他人在途改动，本轮不读取其修改、不提交、不清理。
>
> **授权边界**：用户明确了后置顺序和 Great Lakes 环境。十卡是本次测算情景；下列具体局数、重试预算、新运行名称及十席申请组成执行前的一次确认清单，不能把 V8 原有生成预算挪来使用。本文件涉及后续代码适配，因此按规则保留两部分结构；本轮交付仍只有 Markdown。

# 第一部分（给人看）

## 1. 总览与已定口径

一句话方案：V8 全部收尾后，冻结 V8 新值档交付集（xhard1～xhard5，不含 xhard0），将同一批身份均衡分成十片；十张 A40 各运行一个环境客户端，每张卡先评 SimpleMemVLA、释放模型后再评 MME-VLA，两个模型各覆盖这批新值档身份一遍。

1. **开始时间**：必须等 V8 阶段 1、2、2b、3、3′、3b、4 全部完成并留档，包括换包、xhard0 原计划评估、二次生成及站点检查；不能以 gen1 已完成、站点已生成或 GPU 空闲代替。H2 若存在原计划允许保留 gen1 的正常失败，按原计划预定动作留档即可；不要求把已有 FAIL 改为 PASS，也不将未处理的身份、依赖或产物错误当作收尾。
2. **两个模型**：SimpleMemVLA 官方 RoboMME 权重与 MME-VLA `perceptual-framesamp-modul/79999`，依据现有 `scripts/eval-official/run_seat.sh`；不是 motion/50000 模型。执行前核实最终来源与权重字节，不能仅凭目录名认定相同。
3. **范围（用户 2026-10-02 定）**：只评 V8 新值档交付集 xhard1～xhard5（16 任务 × 43 格，1070 局），**xhard0 不评**；两模型各一遍、单一冻结身份集。xhard0 已由 V8 阶段 3′ 两路线评估覆盖（768 局全部取得终态，见 `docs/validation/newtask-v8/result.md`），本轮不复测、不进分母、不作对照列。此范围用于下述耗时估计，尚不启动。
4. **步数（用户 2026-10-02 定：严格截断）**：交付的 xhard1～5 一律 1600（本轮不评 xhard0，其 1300 不涉及），取自 V8 最终 `hard_specs.TIER_MAX_STEPS`。1600 只数策略执行段的 `env.step`，不含 reset 内生成的演示帧。**执行段累计到第 1600 步仍未成功即直接计为 timeout**（`status=timeout`、`task_success=false`），不再执行第 1601 步，SimpleMemVLA 动作块剩余部分直接丢弃；第 1600 步及之前环境报成功的照常记成功（含恰好在第 1600 步成功，用户已确认）。截断在环境侧共享入口做，两模型同一口径；这改变了现有客户端「按 `count > max_steps` 或按动作块数判停、可能略超」的旧语义，是本轮有意的评估协议变化，不与 V7／V8 xhard0 历史结果逐步对齐。
5. **分数**：每任务、每档分别报告成功率及固定分母，另报全局微平均、任务宏平均、错误数、超时数；缺失不得消失在分母里。记录独立 `task_success`，执行成功不等于任务成功。不为提高成功率重跑正常失败。
6. **范围不外溢**：不改官方 `src/robomme/`、录像器和模型实现；不启动额外采样生成；本次不含把评估视频填回 V8 网站的改造，结果先按留档与媒体索引交付。
7. **全部视频保留（用户 2026-10-02 定）**：2 模型 × 1070 局 = 2140 个正式身份，每局都录像（成功、失败、timeout 一视同仁），基础设施错误与重试的每一次尝试只要录到了画面也保留，不按成败挑选、不抽样；冒烟局视频同样保留，单独目录、不计入正式分母。正式运行禁用 `--no-record`。全部视频搬回本机 `artifacts/v8-evaluation/<run_name>/videos/<策略>/<tier>/<task>/`，GL 侧 NFS 暂存只在逐个 sha256 核对一致后才删；本机副本不删。V7 教训：旧入口 384 个评估视频当时漏搬、事后补搬（`docs/validation/newtask-v7/README.md` ⑥ 视频条），本轮以视频数量闸门堵住。

### 1.1 每个模型的身份数

| 任务组 | 难度与每格局数 | 每模型局数 |
|---|---|---:|
| PickXtimes | 1 任务 × 3 档（xhard1～3，每档分别 17／17／16 局） | 50 |
| SwingXtimes、StopCube | 2 任务 × 5 档 × 10 局 | 100 |
| VideoUnmask、ButtonUnmask | 2 任务 × 4 档 × 20 局 | 160 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 7 任务 × 2 档 × 40 局 | 560 |
| RouteStick、PatternLock | 2 任务 × 3 档（每档分别 27／27／26 局） | 160 |
| MoveCube、InsertPeg | 2 任务 × 1 档（xhard4）× 20 局 | 40 |

记上述完整乘式为 **D**：`1×(17+17+16) + 2×5×10 + 2×4×20 + 7×2×40 + 2×(27+27+26) + 2×1×20 = 1070`。正式评估为 **2 模型 × D = 2140 个策略回合**，不是每模型重复两遍；43 个任务档位格，全部是新值格。按档拆分（取自包内 `hard_specs.EXPECTED_CELLS`）：xhard1 14 任务共 411、xhard2 14 任务共 411、xhard3 7 任务共 128、xhard4 6 任务共 100、xhard5 2 任务（SwingXtimes、StopCube）× 10 = 20，合计 1070。`round` 若在历史文件中出现，不解释为整套重复次数。

## 2. 十卡并行的时间估计

**十张 A40 同时可用、环境预装完毕后，评估运行预计 4～6 小时，排期预留 7 小时。** 不含集群排队、V8 剩余实施与生成时间；评估适配开发、依赖修复不在这个运行时长里。完整流程从现在起的结束时间尚不能确定。

依据是本仓库 [0929 评估提速方案](0929-eval-throughput-plan.md)第一部分的 A40 历史记录：V7 的十分片每轮 SimpleMemVLA 为 100～147 分钟、MME-VLA 为 40～58 分钟；每片共两段身份轮次。V7 单模型身份数为 `16×1×12 + 13×3×20 + 16×1×20 = 1292`，身份分布与 V8 不同。

```text
历史每卡累计时间 = 2 × [(100～147) + (40～58)] 分钟
                 = 280～410 分钟 = 4.67～6.83 小时
按身份数粗缩放   = 上式 × 1070 / 1292
                 ≈ 3.87～5.66 小时
加模型启动、尾片不均衡与结果核验余量：约 4～6 小时，预留 7 小时。
```

交叉核对：同一历史文档记 SimpleMemVLA 累计 146146 秒，即约 40.6 GPU 小时；按 1070/1292 粗缩放后十卡均衡为约 3.36 小时。MME 历史分片累计约 1.33～1.93 小时，同比例缩放为约 1.10～1.60 小时，两者相加约 4.5～5.0 小时，与上述范围同量级。这两种算法共用历史来源，不是两次独立实测。

V8 将新值档上限由历史最高 3800 降到 1600，长失败局可能缩短；同时任务配比、演示长度、编译、reset 与录像成本会改变。**不按 1600/3800 直接缩放整轮，不承诺接近十倍加速。** 10 卡共读 NFS 也可能让加载和录像更慢。正常错误和基础设施重试偏多时可能超出 8 小时。

实施时使用正式运行首批已预算的回合计时，不额外生成测速局。按模型与任务档位统计已完成耗时和剩余身份，报告 `预计剩余时间 = 最慢席位的剩余预计工作秒数 + 收尾余量`；标明尚未观测的格，不拿最快的一局代表全体。

## 3. 为什么需要适配，怎样保持模型行为

现有 `scripts/eval-official/env_client.py::check_identity` 明确只接受 `XHARD0`，`SeatRunner.base_record` 也把档位写死，`source_episode` 必须转整数；新值局这个字段可以为空。V8 的 `export_eval_identities.py::main` 输出 JSONL 的 `episode`，现有客户端 `cmd_run` 读取 JSON 数组并期待 `builder_episode`。因此不能把 V8 清单直接传给旧启动器。

规划的适配只发生在 benchmark 侧。清单转换分四步写死：①核源集——`export_eval_identities.py` 的产物是 1262 行（xhard0 `16任务×1档×12局=192` + 新值 D=1070），先按它自己的判定核总数与逐格数；②筛出五档新值身份 1070 行，xhard0 192 行在这一步丢弃并计数；③导出行不带规格指纹，按 `(task, tier, seed, candidate)` 连接固定的 gen1 交付记录（`V8_DELIVERY_SET` 所核的那份规格行）补齐指纹，连接不上或一对多即停；④对补齐后的执行清单再核 43 格、1070 行、xhard0 为 0、指纹齐全，之后才切十片。随后把 `episode` 显式映射到 `builder_episode`，保留 `tier/seed/candidate/source_episode` 与规格指纹；构造环境前用 `builder.resolve_identity` 逐键核对，按档位得到有效上限 `effective_max_steps=1600`，随后由现有模型客户端推理。**有效上限必须显式透传到两个客户端**：现有 `env_client.run_one` 只把上限放进 `conn_info`，而 `smvla_client.run_episode` 用自己的关键字默认值 `MAX_STEPS`（1300）算 `hard_bound`、不读 `conn_info`——只改 builder 或结果字段会显示 1600、实际仍只跑 `ceil(1300/16)+2=84` 个动作块。适配须以 `max_steps=effective_max_steps` 关键字传入，并在真实调用链上断言 V8 模式为 `ceil(1600/16)+2=102` 块、旧模式仍为 84 块；102 块（最多 1632 步）只是循环保险，真正的 1600 由环境侧截断执行。xhard0 旧身份格式仍须兼容。每局模型 reset 沿用已验证路径；未有证据时不能声称常驻与重启逐位一致，也不为提速新增 batch 推理或更换模型精度。

```text
当前：xhard0 JSON 数组 → 固定档身份检查 → 1300 步客户端 → 原模型 → 动作 → env.step
后续：V8 JSONL(1262) → 核源集 → 筛新值(1070) → 连 gen1 补指纹 → 核执行清单 → 十片身份 JSON → 逐格身份和规格检查 → max_steps=1600 显式透传 → 原模型 → 动作 → 共享 env.step（第 1600 步未成功即 timeout）
```

这一变化改变身份路由和预算，不新增可训练参数；模型输入输出的数据格式、dtype、形状及动作值不应在适配层改动。具体张量形状与字节量沿用两策略原接口，在适配测试和运行记录核实，不凭规划填写未测数字。不同 V8 场景导致不同观测是预期行为，不要求与旧场景逐位相同。

**步数截断的落点**：`mme_client.py` 的循环按 `count > max_steps` 判停，`smvla_client.py` 按 `ceil(max_steps/16)+2` 控制动作块，两者都可能略超 1600。用户已定严格截断（第一部分 §1 第 4 条），落点放在两模型共用的 `env_client.EnvSession.step`：执行段计数到 1600 且未成功时，本步返回后立即把回合标为 timeout 并终止，第 1601 次调用不再进入环境（抛出专用的步数到顶信号由 `run_one` 统一收为 `status=timeout`，不算错误、不触发重试）。不改两个模型客户端的推理与动作块循环本身。结果行同时记 `exec_steps`（必须 ≤1600）、客户端自报步数、动作块数，冒烟与汇总都核这三项。

十席各一张 A40、4 CPU、48 GiB，合计 10 GPU／40 CPU／480 GiB，均为 `chaijy2/spgpu` 的 48 小时占位作业。每席先 smvla 后 mme，任何时刻该卡只有一条评估链；server、client、Vulkan 在同一共享模式步骤内运行。分片按历史任务耗时做贪心均衡，两模型使用相同身份分片。不复用旧 V8 JobID，不擅自取消旧席位；到启动时再核实是否已有明确可转交资源，否则申请本轮新席位。

### 3.1 子代理分工与合并（简述）

改代码按 `CLAUDE.md`「计划执行模式」交给**写入型子代理**做，主会话不直接改这些代码，子代理也不许碰主仓库。拆成三块，文件互不重叠：E-A 管身份清单和两个客户端的适配（含 1600 截断、`max_steps` 透传、reset 额度、尝试账本），E-B 管 GL 十席编排和 tokenizer 闸门，E-C 管汇总报告和视频搬运。三块可以同时开工；E-B、E-C 只依赖 E-A 先定下的字段与命令行约定，这份约定在派发提示里写死。

每个子代理在自己的 git worktree（`.claude/worktrees/agent-<id>/`）里改，每次提交的标题都以 `sub/E-A: `（或 `sub/E-B: `、`sub/E-C: `）开头，只提交到自己的分支、不推送。做完后按 E-A → E-B → E-C 的顺序一个一个合回 `newtaskRelease-taskV8`：**合并前**主会话先核对改动文件没有越出它的可写集合，在它的 worktree 里复跑定向测试，再派一个只读审查子代理对着计划逐项审，结论 PASS 才合；**合并时**用 `--no-ff` 合并提交，子代理的每个 `sub/` 提交原样保留在历史里；**合并后**再跑核心短测、核对文件清单与受保护目录零 diff，PASS 才推送并合下一个。审查 FAIL 就把问题交回原子代理续改，两轮仍不过交用户。GPU 冒烟、真实 GL 运行、留档和最终提交由主会话在三块都合完后串行做。

## 4. 验收与实施顺序

以下是拟新增的验收契约，尚未执行，不能把表内期望行当作已有 PASS。

| 查什么 | 怎么查、通过意味着什么 | 期望判定行 |
|---|---|---|
| V8 真正收尾 | 核对原计划全部阶段报告、换包提交、H2 预定处置和站点证据，不能只匹配完成字符串 | `V8_PREREQUISITE=PASS unresolved=0` |
| 模型与数据身份 | 比较可信权重清单、gitlink、规格哈希与实际导入路径，**以及 MME 实际读取的 `paligemma_tokenizer.model`**（固定 `OPENPI_DATA_HOME`、server 启动前比对独立可信 SHA256），钉死运行对象 | `V8_EVAL_INPUTS=PASS policies=2 identity_count=1070 tokenizer_sha_ok=1` |
| 分片完整 | 按 D 核对43格（xhard0 身份数必须为 0），十片两两不交且并集等于原集 | `V8_EVAL_SHARDS=PASS shards=10 missing=0 extra=0 duplicate=0` |
| 适配与小规模实跑 | JSONL 往返、nullable 字段、xhard5、单 worker 真推理；有演示任务确实生成并录下演示、两模型确实消费了演示历史；1600 截断与 102 块透传成立；不要求策略成功 | `V8_EVAL_SMOKE=PASS infra_errors=0 identity_errors=0 demo_frames_min=<n> exec_steps_max<=1600 smvla_hard_bound=102` |
| 步数截断合同 | CPU 假环境：第 1599／1600 步成功记 success、第 1600 步未成功记 timeout、第 1601 次 `step` 不进入环境；SimpleMemVLA 经真实 `run_one` 调用链拿到 1600 | `V8_STEP_CAP_CONTRACT=PASS cap=1600 over=0 smvla_blocks_v8=102 smvla_blocks_legacy=84` |
| 两模型覆盖 | 每模型按 D 核对逐身份唯一终态——以账本里持久记录的唯一 `accepted_attempt_id` 为准，不按「最后一条」；迟到、废弃尝试不入分数；同一身份出现互相冲突的终态即 FAIL 交用户，不自动择优；错误单列；覆盖通过不表示所有任务成功 | `V8_EVAL_COVERAGE=PASS policies=2 missing=0 extra=0 duplicate=0 conflicting_terminal=0 late_ignored=<n>` |
| 结果与媒体 | 对独立成功字段、退出码、视频终态/解码、报告分母交叉核对；无录像的错误行须明确说明 | `V8_EVAL_REPORT=PASS count_mismatch=0 media_unexplained=0` |
| 视频全量保留 | 按 2 模型 × D 逐身份核对本机视频存在、可完整解码、与 NFS 暂存 sha256 一致；错误尝试的视频另行计数；通过说明 2140 个正式身份一个视频都没丢，NFS 暂存可清 | `V8_EVAL_VIDEOS=PASS policies=2 expected=2140 videos=2140 missing=0 decode_fail=0 sha_mismatch=0 error_attempt_videos=<n>` |

| 阶段 | 内容 | 进入下一步的条件 |
|---|---|---|
| E0 | 等 V8 全部结束，冻结输入；一次确认执行清单 | `V8_PREREQUISITE`、运行名和预算获准 |
| E1 | 申请十席并记录 JobID；同时按第二部分 §3 派三个 worktree 写入型子代理实现 E-A／E-B／E-C，按 E-A→E-B→E-C 逐个审查、`--no-ff` 合并、推送 | 三块各自 `PRE_MERGE_REVIEW=PASS` 与 `POST_MERGE_REVIEW=PASS` |
| E2 | 最小单 worker 冒烟，再检查十席运行环境与端口；冒烟或闸门失败走异常收尾（见 E5） | `V8_EVAL_INPUTS`、`V8_STEP_CAP_CONTRACT`、`V8_EVAL_SMOKE`、`V8_EVAL_SHARDS` |
| E3 | 十席正式评估；失败按类型记账，保留固定分母 | 每身份最终状态与实际尝试账本齐全 |
| E4 | 结果、视频、退出码与预算核验；视频全部搬回本机并核 sha256 后才清 NFS 暂存；留档提交 | `V8_EVAL_COVERAGE`、`V8_EVAL_REPORT`、`V8_EVAL_VIDEOS` |
| E5 | 收尾（成功、失败、中断三种都走）：保存证据与已产出视频，按本轮清单释放自己的 JobID | 原作业和他人资源不受影响；`V8_EVAL_CLEANUP=DONE outcome=<pass/fail/aborted> jobs_released=<n> videos_kept=<n>` |

# 第二部分（技术细节，供 agent 追踪）

## 1. 红线、来源与待验证项

- 不修改原 V8 计划、V8 在途源文件、`src/robomme/**` 或两个策略子模块。受保护目录需要改动时另列具体锚点，不能通过运行时覆盖绕过。
- 不执行旧 `v75-lanes/gl/seat_run.sh`：它硬编码旧 worktree、旧产物位置并包含裸 `python3`。新编排必须使用显式 V8 锚点、当前存储边界和 uv。
- MME 候选 NFS 权重为 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/ckpt/mme/perceptual-framesamp-modul/79999`；SimpleMemVLA 候选为 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme`。依据现有 GL 启动脚本，**本轮未验证路径存在、完整性或最终可加载性**。MME 同时核对父目录 `history_config.txt` 与 `params/assets`，指纹须有独立可信期望值，现场自算仅能记录当前字节。**MME tokenizer 也进资产锁**：锁定源码 `third_party/mme-vla/src/openpi/models/tokenizer.py` 经 `openpi.shared.download.maybe_download("gs://big_vision/paligemma_tokenizer.model")` 读取，缓存命中直接返回、不验哈希；错误但可加载的 tokenizer 会改变文本输入而不改变权重指纹。执行时把 `OPENPI_DATA_HOME` 固定到本轮 `artifacts` 下的缓存目录，server 启动前对该文件比对独立可信 SHA256，不一致即停，不现场下载顶替。**可信值来源（用户已定）**：读 GCS 官方对象 `gs://big_vision/paligemma_tokenizer.model` 的服务端校验和元数据（md5／crc32c），与本地缓存文件现算的同类校验和比对一致后，才把本地文件的 SHA256 记为本轮锁值写进 launch.md；GCS 元数据取不到或不一致即停、交用户，不退回「以现有缓存自证」。
- GL 工作副本以仓库约定 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl` 为基准；执行前确认其归属与状态，不能覆盖其他会话改动。产物落该工作副本 `artifacts/v8-evaluation/<run_name>/`，本机收回到本仓库同一相对根。
- 建议新运行名 `v8-two-policy-gl10-20261001-01`，执行前确认未占用并在一次清单中批准；不能覆盖已有目录。档案放 `docs/validation/<run_name>/`，首次实际启动前记录代码、权重、规格、资源和命令。

## 2. 按文件的拟改动清单

| 文件与稳定锚点 | 拟改动 | 保留行为／依赖 |
|---|---|---|
| 新增 `scripts/eval-official/v8_manifest.py` | 按第一部分 §3 四步：核 1262 源集 → 筛 1070 新值 → 连 gen1 交付记录补规格指纹 → 核 43 格／xhard0=0／指纹齐全；映射 `episode`、输出十片 JSON 和总清单 | 原 `export_eval_identities.py` 不改，原清单 round/shard 为空不受影响 |
| `env_client.py::check_identity`、`SeatRunner.base_record`、`builder_for`、`run_one`、`parse_canary` | 新增显式 V8 模式；档位不写死、nullable 字段严格匹配、结果保留完整身份；`run_one` 以 `max_steps=effective_max_steps` 关键字调用策略的 `run_episode`；`EnvSession.step` 执行段计数到 1600 未成功即发步数到顶信号、`run_one` 收为 timeout；`EnvSession.build`／`reset` 每次实际调用前向持久账本领 reset 额度（两模型共用此入口，MME 直接调 `session.reset()`、两者都先 `session.build()`，均被覆盖），重启进程不刷新；结果行带 `attempt_id` | 旧 xhard0 默认行为和旧 CLI 保留（旧模式不截断、仍 84 块）；builder 缓存须按有效上限区分，避免跨档沿用旧值 |
| `smvla_client.py::run_episode` 的 reset 重试入口 | V8 模式下禁用内部自动重试（`retries=0`）；额度领取不在这里做，统一由 `EnvSession` 共享入口领（见上行），本文件只把异常返回外层统一分类 | 当前 `RESET_RETRIES=2` 代表首试加两次重试，共最多3次；旧模式保持原值；不修改模型推理与动作块循环 |
| `run_seat.sh` 参数解析与客户端启动段 | 透传 V8 模式与重试额度；整合预算不能因进程重启清零 | 原模型启动、reset、清理逻辑保持；新值冒烟不走官方 episode 推导公式 |
| 新增 `scripts/eval-official/run_v8_gl.sh` | 读取固定清单，十席独立输出、tmux 与 srun 编排、进度监督、退出记录 | 不嵌入旧 JobID、工作副本 SHA 或 `/data` 权重默认路径 |
| `scripts/injection-dev/eval_video_mover.py`（搬运入口） | V8 模式：读 V8 结果记录；除终态局外，错误／重试尝试录到的视频也搬（现版只搬 `success/fail/timeout` 终态局，其余会随 NFS 清理丢失）；目标目录按本轮 `run_name` | 原 v7 行为保留；rsync → 两端 sha256 相同 → 才删 NFS 副本 → 写 `moved.jsonl` 的流程不变 |
| 新增 `scripts/eval-official/v8_report.py` | 按持久账本的 `accepted_attempt_id` 取每身份唯一权威终态（不复用 `compare.py` 的「最后一条终态胜出」）；迟到与废弃尝试单列不入分数；冲突终态判 FAIL；任务×档成功率、timeout 数、错误与预算报告、视频索引 | 不用缺失默认零制造成功；每次尝试保留、不覆盖原错误 |
| 新增 `tests/lightweight/test_v8_eval_{manifest,client,orchestration,report,video_mover}.py` | 格表/身份/四步清单转换/1600 截断与 102 块透传/reset 额度跨重启/权威终态与迟到/错误/媒体合同测试及真实 JSON 往返 | CPU 合成夹具不触发仿真，不改变受保护目录 |

## 3. 子代理分配表

执行机制按 `CLAUDE.md`「计划执行模式」：本表经用户批准即为写入型子代理的派发授权，表外不派；用户当前答复为「不开工只审核计划」，**未批准前一个也不派**。

**派发前核对**（主会话，任一不满足不派）：`~/.claude/settings.json` 的 `worktree.baseRef` 为 `"head"`；主检出 `git status --short --ignore-submodules=dirty` 为空（`third_party/SimpleMemVLA` 子模块内容改动是他人在途工作，不算、不动）；记 `BASE=$(git rev-parse HEAD)` 写进本表；`git check-ignore -q .claude/worktrees/probe` 成功；`git worktree list` 存档，已有的 `.claude/worktrees/v7`、`/data/hongzefu/v6-draft/*` 等一律不动。

**派发方式**：三个子代理同一决策点一批发出，各自 `isolation: "worktree"` + `model: "opus"`。提示固定写：子任务编号与目标、可写集合、禁触路径、接口契约、验收命令与判定行、「代码库里不只你一个在改：不碰集合外文件、不回滚他人改动、不改验收命令与判据文件」、「禁止写主检出任何路径（含 Bash 绝对路径）」、「每个 commit subject 以 `sub/<编号>: ` 开头，body 写目标／改动文件／验证命令与判定行」、「不 push、不 checkout／merge／rebase 工作分支、不 amend」、「每条 git 命令单独一次 Bash」、「不得再派子代理、不得起超过 5 分钟的任务」、交回格式（worktree 路径、分支、BASE、HEAD sha、`git diff --name-only BASE..HEAD`、`git log --oneline BASE..HEAD`、验收原始输出、未解决事项、「未派生子代理、未 push」声明）。

**worktree 内验收环境**（本仓库 `CLAUDE.md` 固定取法）：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向测试> -q`；先跑 `… python -c "import robomme_hard; print(robomme_hard.__file__)"`，打印路径必须以 `<worktree>/src/` 开头。worktree 内只跑 `tests/lightweight/` 的 CPU 定向测试；`scripts/eval-official/` 的模块按 worktree 内相对路径导入，同样先打印 `__file__` 核实。GPU 冒烟、`UPSTREAM_GUARD` 等留给合并后主会话。

**公共禁触路径**（三块都适用）：`src/robomme/**`、`src/robomme_hard/**`、`third_party/**`（含两个策略子模块与 gitlink）、`pyproject.toml`、`uv.lock`、`scripts/*.py` 顶层四入口、`1001-newtask-v8-xhard-gradient-plan.md`、本计划文件、`artifacts/**`、`docs/**`，以及其他两块的可写文件。

| 编号／目标 | 可写文件集合 | 禁触路径（公共之外） | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内、上述环境） | 资源占用 | 共享文件归属裁决 |
|---|---|---|---|---|---|---|---|
| E-A 身份清单与客户端适配 | 新增 `scripts/eval-official/v8_manifest.py`；改 `scripts/eval-official/env_client.py`、`scripts/eval-official/smvla_client.py`（只限 V8 模式 `retries=0` 与异常分类，不碰推理与动作块循环）；新增 `tests/lightweight/test_v8_eval_manifest.py`、`tests/lightweight/test_v8_eval_client.py` | `scripts/eval-official/mme_client.py`（MME 不改，截断与额度都落在 `env_client`）、`run_seat.sh`、E-C 文件 | 产出并在交回报告里写死：执行清单 JSON 字段表、`env_client run` 新增的 V8 命令行参数、结果行字段（含 `attempt_id`、`accepted_attempt_id`、`exec_steps`、`status=timeout` 语义）、持久账本文件格式与路径约定 | 1 | `pytest tests/lightweight/test_v8_eval_manifest.py tests/lightweight/test_v8_eval_client.py -q` → `V8_EVAL_ADAPTER_TESTS=PASS`、`V8_STEP_CAP_CONTRACT=PASS cap=1600 over=0 smvla_blocks_v8=102 smvla_blocks_legacy=84` | CPU，无端口、无 GPU、无 tmux | `env_client.py`、`smvla_client.py` 唯一写者是 E-A |
| E-B GL 十席编排 | 改 `scripts/eval-official/run_seat.sh`；新增 `scripts/eval-official/run_v8_gl.sh`、`tests/lightweight/test_v8_eval_orchestration.py` | `env_client.py`、`smvla_client.py`、`mme_client.py`、E-C 文件 | 按派发提示里写死的 E-A 命令行与账本约定调用；固定 `OPENPI_DATA_HOME`、server 启动前 tokenizer SHA256 闸门（GCS 校验和来源）；成功／失败／中断三路收尾输出 `V8_EVAL_CLEANUP=`；tmux 名 `ev-v8-<run_name>-sNN` | 2（E-A 合入后再合；合并前在 E-A 合入后的 HEAD 上复核契约） | `bash -n scripts/eval-official/run_seat.sh scripts/eval-official/run_v8_gl.sh` 退出 0；`pytest tests/lightweight/test_v8_eval_orchestration.py -q`（零仿真假服务：成功、超时、server 死、监督进程死、tokenizer 哈希不符、冒烟失败异常收尾）→ `V8_EVAL_ORCHESTRATION=PASS` | CPU；测试只用临时目录与随机空闲端口，不起真实 server、不提交 GL 作业 | `run_seat.sh` 唯一写者是 E-B |
| E-C 汇总与视频搬运 | 新增 `scripts/eval-official/v8_report.py`、`tests/lightweight/test_v8_eval_report.py`、`tests/lightweight/test_v8_eval_video_mover.py`；改 `scripts/injection-dev/eval_video_mover.py`（新增 V8 模式，旧 v7 行为不变） | `env_client.py`、`smvla_client.py`、`run_seat.sh`、`scripts/eval-official/compare.py`、`step6_summary.py`（不改旧汇总，新报告不复用其「最后一条胜出」） | 按 E-A 结果行与账本约定消费；`accepted_attempt_id` 为唯一权威终态；输出 `V8_EVAL_COVERAGE=`、`V8_EVAL_REPORT=`、`V8_EVAL_VIDEOS=` | 3 | `pytest tests/lightweight/test_v8_eval_report.py tests/lightweight/test_v8_eval_video_mover.py -q`（零缺失、正常失败、错误、重复、迟到、冲突终态、错误尝试视频搬运、sha 不符不删源）→ `V8_EVAL_REPORT_TESTS=PASS` | CPU，临时目录，不碰真实 NFS | `eval_video_mover.py` 唯一写者是 E-C |
| 主会话（不派子代理） | 本计划、`docs/validation/<run_name>/` 与索引；运行产物；合并提交 | — | 派发前核对、三次合并前审查与合并后审查、GPU 冒烟、GL 申请与十席运行、留档提交 | 4 | 合并后核心短测 `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`（失败集合须等于 BASE 既有集合）、`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`、`ls -1 scripts/*.py` 恰 4 个、`UPSTREAM_GUARD=PASS`；之后第一部分验收表全部判定行 | 十张 A40；tmux 前缀 `ev-v8-`；同卡只一个 srun 评估步骤 | 理由：GPU、集群作业、留档与提交切不开、只能串行，归主会话 |

**合并前审查（每块一次）**：主检出 `git status --short --ignore-submodules=dirty` 无非预期改动 → `git diff --name-only <BASE>..<TIP>` 逐项 ⊆ 该块可写集合（越界 `SCOPE=FAIL`）→ 在其 worktree 复跑上表验收 → 派一个只读审查子代理（`model: "opus"`，不加 isolation，钉 `REVIEW_BASE`／`REVIEW_TIP` 完整 sha，只许 `git diff/log/show`），审计划条目是否完成、有无越界、接口契约、`sub/` 前缀与 body、有无凭据／日志／大文件，输出 `PRE_MERGE_REVIEW=PASS|FAIL base=<sha> tip=<sha> files=<n> commits=<n> findings=<n>`。FAIL → 用 `SendMessage` 把 findings 交回原子代理续改，第二轮只复核增量，两轮仍 FAIL 交用户。

**合并与合并后审查**：`git merge --no-ff <TIP sha> -F <scratchpad 消息文件>`（合 sha 不合分支名；subject 按 `12.<小版本>` 体例，body 摘录子代理报告、`PRE_MERGE_REVIEW` 行与改动文件清单）→ 跑上表主会话那一行的短测与闸门 → `git diff --name-only <合并前 HEAD>..HEAD` 与本表核对 → `POST_MERGE_REVIEW=PASS|FAIL merge=<sha> tests=<结果> files=<n>`。PASS 立即 `git push` 再合下一块；FAIL 停止后续合并、不 push、证据交用户，不 reset／rebase。

**清理**：三块都 `POST_MERGE_REVIEW=PASS` 且已推送后，只删本表登记的 `agent-<id>` worktree（`git worktree list` 删前删后各一次、`git worktree remove`、`git branch -d`，未合并分支拒删即保留交用户）。

## 4. 尝试预算与一次确认清单

这是**本轮后续评估的建议预算**，不与 V8 原预算混用。D 的任务×档位×数量乘式见第一部分；策略评估回合按 rollout 记账，回合内 reset 同时计入 reset 预算，两类计数分别核算。

| 用途 | 回合尝试上限 | reset 上限 |
|---|---:|---:|
| 冒烟：2 模型 × [1 任务（VideoUnmask，有演示）× 1 档（xhard1）+ 1 任务（SwingXtimes，无演示）× 1 档（xhard5）] × 1 局 | 4 | 8，暂按每回合最多2次底层 reset |
| 正式：2 模型 × D（D = 1070，乘式见第一部分 §1.1） | 2140 | 4280，同口径 |
| 基础设施重试：2 模型 × 每模型全局最多10次；每身份至多重试1次 | 20 | 40，同口径 |
| 合计 | 2164 | 4328 |
| **reset 预授权上限（用户 2026-10-02：「reset额度可以放开到十倍」「如果有问题可以放开到石碑」）** | 2164（回合上限不变） | 43280 = 4328 × 10 |

上表以 **V8 模式关闭内部 reset 自动重试（`retries=0`）** 为前提；现有 `RESET_RETRIES=2` 实际最多调用3次，不能原样带入本表。现有 reset 捕获所有异常的重试改为 V8 模式返回外层分类：正常场景失败不得重试，只有明确的基础设施故障可消费全局20次额度。**reset 十倍放开**：上表 4328 是默认额度；冒烟或正式运行实测每回合底层 reset（含 build）超过 2 次、或基础设施 reset 故障偏多时，可在不唤醒用户的前提下把 reset 额度逐步放到最多 10 倍（43280，冒烟 80／正式 42800／基础设施重试 400），每次放开都写进账本与日志（`RESET_BUDGET_RAISE from=<n> to=<n> reason=<...>`）；回合尝试上限 2164 不随之放开，正常失败仍不重试、不换 seed、不递补。超过 10 倍即停受影响部分，等用户。额度在 `EnvSession` 共享入口领取，覆盖 `build` 与 `reset` 两类调用、两个模型同一口径，账本持久化、进程重启不刷新。底层 reset 的两倍系数仍是**待验证的设计限额（目前没有静态证据证明它错，也没有证明它对），不是当前代码的实测事实或已证上界**；最小冒烟先记真实嵌套调用，若单次正常回合会超2次，先修正预算并一次说明，不能直接放量。现有启动器客户端重启8次／server重启2次、客户端 infra retry 均不能各自放大本表；它们必须受同一持久账本约束，达到上限立即停受影响部分，重启不得刷新次数。模型加载失败但未开环境，不算 rollout/reset，仍记录启动次数；初始化最多每席每模型首启加一次重启，不无限等待。

冒烟选题：SwingXtimes 全部子任务都是 `demonstration=False`，单靠它证明不了演示生成、录像与两模型消费演示历史的路径，所以每个模型把 xhard1 那局换成有演示的 VideoUnmask（xhard1 有 20 局），保留 SwingXtimes@xhard5 覆盖最高档；冒烟验收要求有演示那局 `demo_frames>0`。冒烟独立于正式统计，不把冒烟成绩当作额外正式样本。额外金丝雀预算为零；十席先做不触发 reset 的输入与服务检查，再执行其分配的正式首局。正常终止、策略失败、到 1600 步计 timeout 均不重试；基础设施故障只重试原身份，不换 seed，不递补新场景。

执行前一次确认（2026-10-02 已定：步数严格 1600 计 timeout、第 1600 步成功记成功、reset 可放开到十倍、tokenizer 以 GCS 校验和为可信源、中午未完成继续跑；**未定：开工授权——用户当前答复「不开工只审核计划」**）：①两模型和权重版本；②完整 D、两模型各一遍及上述尝试上限；③十张 A40、每席4 CPU/48 GiB/48小时；④新 run_name；⑤适配文件清单与子代理写入边界。旧 V8 已批准预算不自动覆盖本表。此时再集中提出未知项，不分阶段重复申请同一授权。

## 5. 运行手册与闸门

下列是未来执行步骤，本轮未运行。先按 `AGENTS.md` 做环境核对，读取最终 V8 报告；确认完成且预算获准后，按 `greatlakes.md` 复用已认证连接、申请占位席。十席超过默认四席，须包含在上述一次确认中。

```bash
# 在 Great Lakes 登录侧，每席一次；名称带本轮 run_name 和席号，记录 sbatch 返回的 JobID。
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 \
  --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=48G \
  --time=48:00:00 --wrap='sleep infinity'
# 占位得到后才派工作负载；实际脚本及参数在适配完成时固化到 launch.md。
srun --jobid=<本轮JobID> --overlap --exact --ntasks=1 \
  --cpus-per-task=4 --gpu_cmode=shared bash <已验证的V8运行器> <本席参数>
```

1. 清点真实工作副本、uv 管理的解释器与权重路径。`UV_LINK_MODE=copy`，显式 `UV_CACHE_DIR=$HOME/.cache/uv`；模型及其他持久缓存落本轮 `artifacts`。计算节点只用 `uv run --frozen --no-sync` 或已核验的 uv venv 解释器，不现场安装。若从编排作业派发，清除继承的 `SLURM_*` 后再显式指定目标 JobID。
2. 在 clean、固定提交的执行副本运行；主检出的子模块在途修改不能带入，不能替别人提交或清理。本机与 NFS 通过 rsync 同步输入，核 SHA256；记录实际 import 路径，不能误用旧包。
3. E-A 按四步转换输出十片及 manifest，并保留原 JSONL（1262 行）哈希、筛掉的 xhard0 计数（192）与补指纹所连接的 gen1 记录哈希。每模型身份集合必须等于 D（1070，43 格）；执行清单含任何 xhard0 身份或缺指纹即停。不重新生成或重新抽签。xhard0 本轮不评。
4. 启 server 前先过 tokenizer SHA256 闸门。先跑冒烟表的第一项（1 模型 × VideoUnmask × xhard1 × 1 局、单 worker），通过后串行完成剩余三项。核对真实 reset 次数（含 build）、`exec_steps≤1600`、SimpleMemVLA `hard_bound=102`、`demo_frames>0`、模型 reset 和结果格式；失败不直接启十卡，转第 9 步异常收尾。
5. 十席 tmux 命名 `ev-v8-<run_name>-s00`～`s09`；独立输出 `<root>/sNN/<policy>/`。端口按 `18000 + 100×席号 + 10×策略号` 起，先探服务与相邻端口，冲突有限次换位。server就绪与首次推理分别设超时，不能把监听成功当作首次推理可用。
6. 每任务命令用 `PYTHONUNBUFFERED=1`、`set -o pipefail` 和 `tee`；结果持久化后写 `EXIT_CODE`。持久监督器覆盖主进程死亡、无进展、日志/报告写失败；独立测试监督器自身崩溃的通知路径。不得仅凭 tmux 存活宣称有自动唤醒；本轮未注册后台启动或唤醒。
7. 结果齐全后运行汇总，核每格分母、终态、退出码、预算及媒体；录像结束后再解码检查。视频全部回传本机（必做，见第一部分 §1 第 7 条）：评估期间可常驻运行 `eval_video_mover.py` 边跑边搬，评估结束后再 `--once` 全量对账；每个文件 rsync 后两端 sha256 相同才删 NFS 副本，本机副本一律不删。`V8_EVAL_VIDEOS=PASS` 之前不得清理 NFS 评估目录或释放占位作业里仍有未搬视频的席位。
8. **无人值守与时限（用户已定）**：用户开跑后去睡觉，回来时间为东部时间中午 12 点；到点未跑完**继续跑到完成**，48 小时占位作业足够，中午只出一份中途进度（已完成身份数、各格成功率、预计剩余时间、异常），不停作业。主会话未注册任何后台唤醒，会话断开后作业仍在 tmux 内继续、监督进程负责失败停机与收尾，但最终汇总、提交与释放资源要等主会话恢复后再做；不得对用户承诺「睡着期间一定会自动处理完」。
9. 收尾分三路，都要走完：**成功**——全部闸门通过、视频搬完后留档并释放；**失败**（冒烟失败、闸门 FAIL、预算耗尽）——停受影响部分，保存日志、结果行、已录视频（照常搬回本机核 sha256）与失败判定行，写 `result.md` 失败段，再释放本轮 JobID；**中断**（用户叫停、作业到期、节点故障）——精确停本轮 tmux，记录停在哪一身份与未完成范围，同样先搬已产出视频再释放。三路都输出 `V8_EVAL_CLEANUP=DONE outcome=<pass/fail/aborted> jobs_released=<n> videos_kept=<n>`。只释放本轮清单里的 JobID，tmux 只按精确名称逐个清理；禁止全用户取消和全局杀 tmux。

测试命令模板：核实 `command -v uv`、`pyproject.toml`、`uv.lock` 后，以显式缓存目录运行 `uv run --no-sync python -m pytest tests/lightweight/test_v8_eval_manifest.py tests/lightweight/test_v8_eval_client.py tests/lightweight/test_v8_eval_orchestration.py tests/lightweight/test_v8_eval_report.py tests/lightweight/test_v8_eval_video_mover.py -q`；这些测试文件是拟新增项，当前不能直接运行。真实冒烟只在 E2 进行，计入上表。

## 6. 风险与盲区

- **耗时不是实测保证**：4～6小时来自 V7/A40 历史分片；排队未知、V8 分布变化和 NFS 争用尚未测。本轮没有登录 GL 查询空卡。
- **推理等价未扩大承诺**：沿用现有模型实现不自动证明不同机器、常驻与重启逐位相同；如缺必要验证则在 E2 阻塞相应优化，不用成功率一致替代动作一致。
- **reset预算须落到实际入口**：底层演示生成可能含额外 reset；入口隐含重试也可能放大次数，必须在冒烟实测并限制。
- **截断改变可比性**：严格 1600 截断后，本轮成功率与 V7、V8 xhard0 历史结果（旧循环可略超上限）不是同一协议，不做逐局对齐；接近上限才成功的局会被记为 timeout。
- **运行器能力缺口**：当前 xhard0 客户端不能直接评新值档；拟新增判定行、十席控制器、完整媒体汇总尚未实现。
- **原计划在执行**：读取锚点是阶段2收尾提交，不能由此认定V8完成；后续一定重新核实阶段3、3′、3b、4的证据。
- **视频体量**：V7 两策略评估视频 2590 个、本机共 5.6 GB（`artifacts/newtask-v7/eval-videos`），按此估本轮约 5 GB 量级，本机 `/data` 剩余约 3.5 TB，不构成约束；NFS 暂存体量随搬运进度波动，未实测。
- **十卡资源只是情景**：不将旧7个占位作业视为本轮十张可用卡；排队、到期、配额和转交都需到执行时核实。

## 7. 留档与提交纪律

本轮只提交本文件，执行 `git diff --check`、链接/章节/乘式核对与明确路径暂存；不运行 Python、仿真、测试或集群任务。后续代码适配按各块定向测试，整合后冻结正式执行提交。

正式运行档案保存 `launch.md`、`result.md` 与 `records/`：启动版本、模型/数据指纹、用户确认原话、十席清单、完整命令、实际 reset 与 rollout 尝试、时间估计更新、成功率、错误、视频索引与退出码。更新 `docs/validation/` 的现有索引入口；只保存 Git 无法还原的结果，不拷贝脚本、配置、权重。任何 PASS 均附实际命令、退出状态、输出路径和审查范围；没有执行的项目写未验证。
