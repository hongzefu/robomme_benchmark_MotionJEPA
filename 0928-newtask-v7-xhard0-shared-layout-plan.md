# 0928 方案：test-hard v7 —— 接入 xhard0（原生 hard）+ xhard1～4 改为共用 20 个母布局（只规划不实施）

> **权威性与锚点**：本方案是 v7 的唯一现行计划，取代 12.222 的 `0928-xhard0-native-hard-plan.md`（已于 34c4164d 从工作树删除，取回用 `git show 8dfd09cb:0928-xhard0-native-hard-plan.md`）里「xhard0 追加在旧四档之后」的编号建议与「xhard0 只是评估身份、不生成 h5」的口径（后者已被用户原话 13 推翻，见 §2）；其余 xhard0 结论（身份来源、原生分支）原样沿用、本文只引用不重抄。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-v5`，代码锚点 `8dfd09cb`（12.222；本次修订时 HEAD 为 `a90efc0f`，12.231，其间 `src/`／`scripts/`／`tests/` 零改动，`git diff --stat 8dfd09cb a90efc0f -- src scripts tests` 为空）。官方源码锚点 `1fadc0ec`（`src/robomme/` 逐字节相同），官方编排锚点 `d53f21a7`（`scripts/parity/official/` vendor）。commit 编号沿用 `12.<小版本> 中文描述`。**12.232 及之前各版只写方案；2026-09-29 用户逐条拍板起跑前全部未决项（原话 24、第四次修订）后，12.233 起进入实施：用户已对第二部分 §2 预算全表一次性批准（原话 12、24），阶段 0～11 按表连续执行、不逐阶段等确认，只有判定 FAIL、超出预算或触发 §1 第 9 条明写的硬线才停下找用户。**
>
> **用户原话（2026-09-28，按时间顺序逐字保留）**：
> 1. 「给出方案 xhard现在有1-4 再加入xhard0 需要和原本的hard保持完全一致 每个task episode数量和以前一致 根目录写方案」
> 2. 「xhard1234改为同样reset布局 总共20个布局 只有现在的梯度区别不一样」（附四档梯度表，与 `scripts/README.md` 第 3 节逐字相同）
> 3. 「并且告诉我现在的多卡容差范围是多大 为什么」
> 4. 「保证接口和现在一致 /data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/README.md」
> 5. 「修改完定为v7的task」
> 6. 「拍链路（parity/）只需要原三档 144 局清单（16 任务 × 3 档 × 3 局）和新的v7 两次生成一致」
> 7. 「需要修改parity机制 我要的是每次都和保存完的o对比 p读取之前的commit 来对比 给这个commit锚定要打上tag 每次都是oph o上传 p回到之前commit 以及h现在 不要以修改前后 每次都锚定固定的commit 以后都这么干」
> 8. 「对于v7 现在这个commit已经做完之前的v6 oph parity 修改后再做一次v6的oph parity 然后存档 之后都只以新的v7 打tag做parity」「验证过的commit就不用再次验证了」「另外这些都是基于a40 的容差标准？」
> 9. 细化方案经用户回复「同意」（2026-09-28）；三个待定项用户未另选，按推荐落定：v6 xhard 165 局纳入 v6 回归、O 以本机 `/data` + 逐局 sha 清单为准（bucket 被 HF 计费拒绝；**后经 12.213 核实已全部上传公开 bucket `HongzeFu/robomme-hard-parity`，本机 `hard-split/h5/` 已清空，O／P 缓存一律以 bucket 为准**）、tag 名 `parity-anchor-v6`／`parity-anchor-v7`。
> 10. 「生成的job我已经query过了在排队」「也是直接用」（生成阶段直接用用户已提交排队的占位 job，不另提）。
> 11. 「评估的job你自己提交 但是参考framesample 的实测说明了两件事：1 CPU主要让启动阶段变慢。 第一次处理请求，1 CPU约183秒，4 CPU约61秒；等前期编译结束，每次取一组动作都约0.22秒，差别很小。保持模型常驻确实有收益。 两个任务分别启动，合计约6分钟；只启动一次、连续跑两个任务，约3分39秒。这次省了约2分19秒，但还不是完整三轮比较。」「模型常驻先不动 保持一致 cpu改为4个」
> 12. 待决项经 AskUserQuestion 定（2026-09-28）：P3 预算「全表一次批准」；xhard0「12 局」；四档同废「接受，30 个候选」；产物「gen2 比完即删」。
> 13. 「xhard0你理解错误 我需要走/data/hongzefu/robomme_benchmark_MotionJEPANewTask/src/robomme_hard路线生成+评估，生成和评估的结果都要和以前一致」
> 14. 「原版评估和生成 零食用一个https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen来实现」（「零食用」按上下文读作「都是用」：官方的评估与生成都由 `dataset-gen` 分支实现）
> 15. xhard0 新增四行预算（生成 O 侧 192、H 侧 192、reset 层对拍 384 次、官方路线评估 2 × 192）经 AskUserQuestion 一次性批准：「全部四行批准」（2026-09-28）。
> 16. 「梯度（每档现场抽）	低档物体更少时怎么取 你这两个在说什么 干扰的不也是梯度的一部分吗？ 低档物体更少时怎么取只说怎么取前k个 重写这个表格」（12.230.2 已落：物体数量归入梯度列）
> 17. 「现在的梯度都不要取区间了 直接定死数字 保留确定性 都取上界 干扰容器数 8 → 10 → 13 → 15和 外环干扰数 4 → 6 → 8 → 10 这些地方 所有的xhard1 能否做到只比xhard0难一点点 保证梯度的均匀 给出方案」
> 18. 「注意这个外环干扰要和内环加起来 和unmask xhard0实际生成的数字对比 我要的是目视语义结果的梯度」
> 19. 「（内环 15）实际生成多少？有一部分取不到的！ 有哪些任务是有生成浮动的 你也要挖清楚了」
> 20. 「h5有segementation 你来测！给出定值」（核实：h5 只落 RGB／深度，无分割；据此指令用官方环境按 xhard0 的 12 个 seed 跑 reset 探针，7 任务 × 1 档 × 12 局 = 84 次，见 §3.2.1）
> 21. 「把这个详细展开的要写进计划」（附 §3.2.2 定值表原文）
> 22. 「参考…codex的审计 根据最新的计划 给出新的审计意见 如果不够再启动subagent 全sonnet 在调查一波」；随后「有哪些问题需要用户注意 先详细解释 再让用户决策 其他的你自行修改」。
> 23. 四个决策项经 AskUserQuestion 定（2026-09-28）：BinFill「A 嵌套派生」；xhard0 评估判据「A 环境层判、策略层只报告」；VideoPlaceButton／VideoRepick 母布局抽签上限「A 两任务提到 100 次」；修补所需追加预算（阶段 1 的 55 次 reset、阶段 3 净增 16 次 reset 与 16 条轨迹、阶段 7 的 2 局冒烟）「全部批准」。
> 24. 起跑前未决项逐条拍板（2026-09-29，按 agent 列出的条号逐字保留）：「a1 t同意」「a2 保留」「a3 一路跑完」「a4 全部跑完」「b1 第一种」「b2 增加候选」「b3 预定规则。同时保留一条硬线：任何一个 pair 里超容差的局数超过 5% 时，不管分类结果都停下找你，因为那已经不是零星噪声。」「b4 上调上限」「b5 现在data释放了 只删除重复的缓存对拍和已经放在bucket的内容 尽可能不要停」「C. 干扰色 你自己目视决定」。条号含义见 §1 第 9 条。
> 25. 「还有什么没定 能一口气跑完吗」「生成job用那些a40 占位？」「生成完毕后还是释放 只保留1个展位job」（2026-09-29；答复与落定见 §1 第 9 条 A5、A6）。
> 26. 实施开始后（2026-09-29）经 AskUserQuestion 定：B3 替代口径「按首个分叉步判（推荐）」；PatternLock「直接改 12/15/18/21」。
> 27. 阶段 1 补核对预算：「批准 ≤16 次（推荐）」。
> 28. 「批准 ≤24（推荐）」（阶段 3 reset）；「批准增至 768 次（推荐）」（阶段 7 xhard0 reset 层对拍）。
> 29. 「批准增加Reset次数增加到原来的十倍都可以。」
> 30. 「不要再问我了尽可能一路做到东部时间明天早上10点。」；此前另有「继续 注意有一个评估报告被清除了 作为不可靠结论 目前计划仍旧采用上一次v6生成的eval分法 只是增加4cpu档位」（12.235 已清除 `docs/validation/eval-cpu-20260928/`，本文引用其数字处一律作废，只保留「CPU 改为 4」）。
>
> 上一轮（12.222）关于 xhard0 数量的最后决定：「和test的hard数量一致」→ 每任务 12 局。本文对原话 1 里「每个task episode数量和以前一致」的解读：**xhard0 每任务 12 局（沿用 12.222 决定），xhard1～4 每格仍 20 局（与现在一致）**。用户 2026-09-28 已确认 xhard0 取 12 局（原话 12）。

**2026-09-28 修订（原话 13、14）**：此前本文把 xhard0 只当「评估身份」——评估走 `robomme_hard`，但不生成 h5、不与官方对拍，轨迹比较列为可选项。用户纠正：xhard0 的**生成与评估都必须走 `src/robomme_hard` 路线**，且两者的结果都要与「以前」一致；「以前」= 官方 `dataset-gen` 分支的实现（生成编排 `d53f21a7`、环境源码 `1fadc0ec`，两个锚点均在 `origin/dataset-gen` 上，`git merge-base --is-ancestor` 核实）。据此改写 §2、§5、§6 与第二部分 §1.5、§2、§3、§7.5～7.7；新增的生成／评估预算行已由用户一次性批准（原话 15），与原表同等效力。

**2026-09-28 第二次修订（原话 16～21）**：此前本文（决策 3、D-5、R3）写的是「梯度数值沿用现行四档表，一个不改」。用户改为：**全部梯度定死为单个数字、不再取区间；物体数量按桌面目视总量（内环 + 外环／干扰）算梯度，基线是 xhard0 实际生成的数量而不是配置数；xhard1 只比 xhard0 难一点点、四档等差。** 为此先用官方环境实测了 xhard0 的实际放置数（§3.2.1），再据此定表（§3.2.2）。受影响段落：决策 3、§3.1、§3.2、§3.3、§6 阶段 1′、第二部分 R3、§1.7、§2、D-5、§7.3.2、§7.6、§5。

**2026-09-28 第三次修订（原话 22、23；审计锚点 `a90efc0f`）**：本版吸收三份审计——Codex 两轮（锚点 `43c4f83f`、`eb929364`）、Claude 两轮（`43c4f83f` 的 48 条、`a90efc0f` 的新增 19 条），合并去重后逐条落进正文。用户拍板的四项（原话 23）写成 D-15～D-18；其余按「不改变设计意图、只把机制写对」的原则由 agent 自定（D-10）。主要改动：①派生接线改为 `native_episode_spec` 的 derive 信封，13 个环境文件不改（§1.2）；②白名单改为 L／G／N 三表闭世界，漏写即报错，并加动态门禁 `LAYOUT_WHITELIST_COMPLETE`（R10、§1.3）；③BinFill 投入按嵌套派生（D-15）；④UnmaskSwap 在注入后的实际布局上重新规划，分层模式下不再做 `same_geometry` 比对（§1.8）；⑤第 4 干扰色另设 `BLOCK_DISTRACTOR_COLORS`，不动 Unmask 共用的三色池（§1.7）；⑥删去 PickXtimes「漏改」行（前提不存在）；⑦xhard0 评估一致由 reset 层确定性部分判定，策略层只报告（D-16）；⑧gen1／gen2 统一经 `hard_parity.py` 登记身份与 A40 断言（§1.4、§1.5）；⑨`spec_binding` 对 xhard0 的期望改为 `mode=export`；⑩预算补合计行与追加项（D-18）。逐条对照见第二部分 §8。

**2026-09-29 实施中修订（原话 26～30；只追加，原话 21 附表等原文不改）**：①PatternLock 定值改为 12/15/18/21（原话 26；原表 12/16/20/24 的 24 在 v6 实测 30 个 xhard4 候选里只出现 1 次，搜不出路径），§3.2.2 表中 PatternLock 一行以此为准；②B3 的「RRT 重规划次数不同」无处记录（O 侧官方 `_worker` 原样不能计数），改为「setup／结构／成功与否都相等且 `first_divergence>0` → noise，否则 FAIL」，5% 硬线不变（原话 26）；③reset 预算各行上限按原表 ×10（原话 29；轨迹与评估局数不变），据此阶段 4 母布局抽签上限取每任务 500、VideoPlaceButton／VideoRepick 1000；④D-19：Swap 两任务外环在低档取母布局外环按角度序的一段可行连续弧（阶段 1／3 实测 BUS xhard1 按放置序取前 2 个全部被按钮避让 `btn` 拒绝）；⑤D-20：xhard0 reset 层对拍的「演示前状态」每局另起一次底层环境 reset 取 `get_state_dict()`（官方 reset 内部直接跑演示且不许插桩），预算 384 → 768（原话 28）；⑥评估分法沿用 v6（每轮每格 10 局、xhard0 每任务每轮 6 局），只把 CPU 改为 4（原话 30 之前一条）；⑦worktree：实施在 `.claude/worktrees/v7-run`（分支 `v7-run`），每次 commit 后快进同步 `newtaskRelease-v5`（用户 2026-09-29「用一个新的worktree 然后每次commit完同步主branch」）。

**2026-09-29 第四次修订（原话 24；起跑前决策）**：用户要求「起跑前全部决策完」，agent 列出 10 条未决项（范围与节奏 A1～A4、运行时闸门预定处置 B1～B5、干扰色 C1）并逐条给推荐，用户逐条拍板，全部写入 §1 第 9 条；B2 的追加候选预算写入第二部分 §2；B3 的分类规则与 5% 硬线、B4 的上限公式、B5 的腾空间顺序改写进第二部分 §4 风险登记对应行。本版起进入实施，不再逐阶段等确认。

# 第一部分（给人看）

## 1. 定好的决策

1. v7 的 `test-hard` 从 4 档变成 5 档：新增 **xhard0**，放在 xhard1 前面。
2. xhard0 就是原来官方 test 里的 hard，一局不改：16 任务 × 1 档 × 12 局 = 192。**生成与评估都走 `src/robomme_hard`**，并分别与官方 `dataset-gen` 路线对拍：生成出的 h5 与官方生成器的产物在容差内一致（同型号 A40）；评估一致由 reset 层判定——两条路线建出的场景（演示回放前的仿真状态、任务目标、选项、seed）逐位相同；策略层两路各评 192 局只报告终态差异、不作判定（D-16：策略推理本身不确定，同一路线重启一次步数就会变，终态全同不是可证的判据）。
3. xhard1～4 **四档共用同一批 20 个场景布局**。四档之间只有难度梯度不同（次数、数量、序列、演示选择）。**梯度数值按 §3.2.2 定值表：每档一个定数、无区间；物体数量按桌面目视总量等差，基线是 xhard0 实测放置数（§3.2.1）；xhard1 只比 xhard0 难一点点**（原话 17～21）。这推翻了本文初版「一个不改」的口径，v6 四档表只作历史对照。
4. 局数：13 任务 × 4 档 × 20 局 + 3 任务（StopCube／InsertPeg／MoveCube，只有 xhard4）× 1 档 × 20 局 = 1100，加上 xhard0 的 192，共 1292。
5. 评估接口不变（`scripts/README.md` 第 1 节那 4 处）：只多一个档名 `xhard0`，它的步数上限是 1300。
6. parity 改为**固定 tag 锚点**，以后都这么做（§4）。
7. 容差只在 A40 + 同一驱动上成立；正式生成与对拍一律在 GL 的 A40 上跑（§4.3）。
8. 共用布局的实现细节已按三份审计改正（引言「第三次修订」、第二部分 §8）：BinFill 低档投入按母档嵌套派生（D-15）；白名单闭世界；UnmaskSwap 在注入后的布局上重新规划；第 4 干扰色只给 PickXtimes／SwingXtimes 用。
9. **起跑前决策（2026-09-29，原话 24）**——以下每条中途不再问用户：
   - **A1 官方路线对照轮保留**：阶段 10′ 每策略 16 任务 × 1 档 × 12 局 = 192 照跑，只报告不判定（D-16）。
   - **A2 阶段 5 的 v6 回归保留**：H 侧 144 + 165 = 309 局照跑，阶段 0′ 照原样拉回 O／P 缓存。
   - **A3 阶段 9～11 在本轮范围内**：阶段 8 发布后发简报、不等回复，直接切策略分支、提评估 job。
   - **A4 连续跑到阶段 11**：每阶段结束发进度与判定行，不等确认；只有 FAIL、超预算或本条硬线才停。
   - **B1 阶段 0′ 等价核验失败时**：不重新生成，tag 打回实际生成的两个 commit（`parity-anchor-v6-native` → `34a1ceab`、`parity-anchor-v6-xhard` → `b1afc804`），登记表按段记 tag。
   - **B2 阶段 4 某任务 30 候选凑不齐 20 局时**：该任务追加一轮 30 候选（抽签上限同原表：该任务 50 或 100 次）并派生三档，预算已批（§2「追加候选」行）；追加后仍不足则接受该任务少于 20 局并留档，不做第二次追加，不放宽定值表。
   - **B3 阶段 5／5′／6 对拍超容差时**：按预定规则分类——`first_divergence` 在该局首次 RRT 规划之后且两侧 RRT 重规划次数不同 → 记 `noise`、只报告不判 FAIL；`first_divergence` 在 reset 或首次规划之前 → 判 FAIL 停。**硬线**：任一 pair 内超容差局数超过该 pair 局数的 5%，不论分类一律停下找用户。容差本身不放宽、不重标。
   - **B4 `V7_STEP_HEADROOM` 超上限 90% 时**：不回调抓取次数，把该档 `TIER_MAX_STEPS` 上调为该档实测演示最大步数 × 1.25 向上取整到百，改动记入留档与 README。
   - **B5 本机磁盘**：`/data` 已释放（2026-09-29 `df -h /data` 剩 5.2T），原「预计超 2T 停下问」的停线撤销；只删重复的对拍缓存与已在 bucket 的内容（顺序：拉回的 O／P 缓存 → `PARITY_V7_TWICE=PASS` 后的 gen2 → 已 `BUCKET_SYNC=PASS` 的 xhard0 O 侧），评估视频与 gen1 不删；尽可能不停，三项删完仍不够才停。
   - **C1 第 4 干扰色**：阶段 3 出图后由 agent 目视自定，橙色不过关就换与三色池及目标色色相距离最远的备选色，不问用户。
   - **A5 生成占位 job 清单（原话 25，2026-09-29 查询 `squeue`）**：生成阶段（4、5、5′、6）只用用户已提交的四个 16 CPU／192G／1 GPU 占位 job——`62126062`（hs-hold-20260927-3，RUNNING gl1506，查询时剩约 19.5 h）、`62268733`（v7-hold-20260928-1，RUNNING gl1525，剩约 42 h）、`62268734`（v7-hold-20260928-2，PENDING Resources）、`62268735`（v7-hold-20260928-3，PENDING Priority）；不另提生成 job。分配：阶段 4 与阶段 5 先用在跑的两个；阶段 5′ 的 O／H 两侧、阶段 6 的 gen1／gen2 各需两个不同 job，等 PENDING 的两个上线后再起。`62126062` 若在阶段 4 起跑前到期就顺其自然，不续提。同名下的 `eval-*` job 属另一条评估线，不在本清单，不碰。
   - **A6 生成完毕即释放、只留一个（原话 25）**：阶段 6 的 gen2 经 `hard_pull` 拉回本机、`PARITY_V7_TWICE` 判定行出现后，按 A5 清单逐个 `scancel` 生成占位 job，只保留**当时剩余 walltime 最长**的那一个，JobID 写进留档并打印 `GEN_HOLD_RELEASE=PASS kept=<JobID> cancelled=<n>`；阶段 9 提的 10 个评估 job 在阶段 11 按清单逐个取消，最终名下只剩这 1 个占位 job。绝不 `scancel -u`。

## 2. xhard0

- **是什么**：官方 test 元数据里每个任务 `difficulty=="hard"` 的那 12 局（原 episode 号 3,7,…,47），seed 逐条照抄元数据。16 任务 × 1 档 × 12 局 = 192。
- **「以前」是什么**：官方 `dataset-gen` 分支——生成用 `scripts/data-generation/generate_dataset.py`（本仓库 `scripts/parity/official/` 逐字节 vendor 自 `d53f21a7`），评估用 `scripts/evaluation.py` + `robomme.env_record_wrapper.BenchmarkEnvBuilder(dataset="test")`，环境源码 `1fadc0ec`（`src/robomme/` 与之逐字节相同）。两个 commit 都在 `origin/dataset-gen` 上。官方公开数据集只有 train 100 局／任务，**test 的 hard 从没有公开 h5**，所以「以前的生成结果」只能由官方代码现场生成得到（O 侧），不是下载来的。
- **怎么生成（走 `robomme_hard`）**：`generate` 的 H 侧 worker 不再自己拼 `gym.make` 参数，而是先构造 `robomme_hard` 的 `BenchmarkEnvBuilder(task, dataset="test-hard")`，用 seed 找到对应的 xhard0 条目，取它给评估用的那份环境参数（`seed` + `difficulty="hard"`，无 `sampling_config`、无 `native_episode_spec`），再套官方生成链（`RobommeRecordWrapper` + 规划器 + `_execute_tasks`）。H 侧 worker 是 `train_split_worker.py::run_one`——官方 `_worker` 的 `gym.make` 参数表镜像，规划与执行直接调用 vendor 的 `_planner_classes`／`_execute_tasks`，另外多写 `rng_trace.json`／`episode_spec.json`；它不是 vendor `_worker` 本身。这样生成和评估拿到的是**同一份**环境参数，不会出现「评估走 builder、生成走另一条路」的分叉。runner 对 xhard0 的身份复核走新增的第三种来源 `test_metadata`（第二部分 §1.5），现有 `train_metadata` 会把 test 身份判成不符而直接退出。
- **导入边界**：只要求单向——官方侧（O 侧生成、官方路线评估、reset 层对拍的官方子进程）不得导入 `robomme_hard`（R9）；`robomme_hard` 本身借用 `robomme` 的若干模块（如 `episode_config_resolver`、`FailAwareWrapper`），H 侧导入 `robomme` 是设计内的。
- **怎么评估（走 `robomme_hard`）**：`evaluation_hard.py` 不改，`dataset="test-hard"` 的 episode 0～11 就是 xhard0，`resolve_episode` 返回 `(seed, "xhard0")`，步数上限 1300（与官方 `evaluation.py` 默认一致）。
- **「一致」怎么证明**（两条，都是 192 局全量、不是抽样）：
  1. **生成一致**：O 侧 = 官方 `_worker` + `robomme`（`1fadc0ec` worktree），H 侧 = 上面的 `robomme_hard` 路线；两侧同一批 192 个 job（task、原 test episode 号、seed、`difficulty="hard"`），都在 GL 的 A40 + 驱动 595.71.05 上生成，`compare --pair O:H --tier xhard0` 按现行容差判 → `PARITY_O_H=PASS tier=xhard0 shape=16x1x12 compared=192`。O 侧上传公开 bucket 永久复用（D-11），H 侧产物在 v7 验收通过后登记为 `parity-anchor-v7` 的 P 缓存。
  2. **评估一致（D-16，用户原话 23 选「环境层判、策略层只报告」）**：分两层。
     - ①**reset 层（判定）**：同一张卡上两个进程，一个只导入 `robomme`（`dataset="test"`，原 episode 号），一个导入 `robomme_hard`（`dataset="test-hard"`，episode 0～11），各自 `make_env_for_episode` + `reset`。**确定性部分**逐位相同才 PASS：演示回放开始前的 `env.unwrapped.get_state_dict()`、seed、`task_goal`、多选项列表，以及两侧 `gym.make` 实参与包装链类名序列 → `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0`。**演示部分**（演示帧数、演示帧、演示后状态）只报告：`reset()` 里演示会走螺旋规划、失败转 RRT*（`DemonstrationWrapper.get_demonstration_trajectory`），受墙钟时间影响；v6 评估实测 `EVAL_DEMO_FRAMES=INFO exact=1054 within_5=1096 max_diff=19`（`docs/validation/newtask-v6/hard-split/stage7-eval.md`），约 4% 的局演示帧数本来就不同，逐位要求会误报。
     - ②**策略层（只报告）**：SimpleMemVLA 与 MME-VLA 各用官方 `evaluation.py` 路线（`robomme`，`dataset="test"`，只跑 hard 那 12 局／任务）再评 192 局，与 v7 正式评估里 xhard0 的 192 局按 seed 对齐，列出终态（`status`）与步数的差异 → `XHARD0_EVAL_PARITY=INFO policy=<名> compared=192 status_diff=<n> steps_diff=<n>`，不作判定、不因差异重跑。原因：12.212 的「终态 1100/1100 相同」只覆盖 SimpleMemVLA；`docs/validation/eval-cpu-20260928/` 实测 framesample 在同节点同卡同身份上，仅启动方式或 CPU 配额不同，PickXtimes/xhard1/ep0 步数就是 755／605／605／600、VideoPlaceButton 是 162／175，策略自身的噪声会淹没路线差异。
- **一个官方细节照抄不改**：官方 `_worker` 的失败恢复模式按 episode 号定（≤2 用 `z`、≤5 用 `xy`、其余关），xhard0 的 job 用原 test episode 号，所以只有 episode 3 那局带 `xy` 恢复，其余 11 局不带；O、H 两侧完全相同，不另加 `--no-recovery`（那会偏离官方生成器原样）。评估路线（官方与 `robomme_hard` 都一样）从不开恢复，与生成路线的这点差别是官方本来就有的。
- **为什么不和 xhard1～4 共用布局**：原生 hard 的场景是官方代码在 hard 配置下抽出来的；换成 xhard 的布局，它就不再是「原来的 hard」。

## 3. xhard1～4：改前 vs 改后

### 3.1 总的变化

| | 改前（v6，现在） | 改后（v7） |
|---|---|---|
| 场景布局 | 每档各抽各的，四档 seed 段不同（6e6／8e6／10e6／12e6），同一局号在四档里的场景没有关系 | 每任务先在 xhard4 配置下抽 20 个「母布局」，xhard1～3 直接沿用；四档同一 seed（`14e6 + 任务码×1e5 + 候选×100 + attempt`） |
| 难度梯度 | 各档按自己的区间抽（如抓取次数 [6,7]） | **每档一个定数、不再抽区间**（§3.2.2）；数量类梯度按桌面目视总量等差，以 xhard0 实测数为基线（§3.2.1）；仍在环境里按本档配置现场取值，只是取值集合缩成一个点 |
| 低档物体更少 | 各档独立摆放 | 从母布局里取**前 k 个**（母布局按 xhard4 的最大数量摆，低档用得少就取前面几个，位置、颜色都不变） |
| 某档在某个布局上抽不出合法场景 | 该档单独换一局 | 这个布局在四档**同时作废**，四档一起换下一个候选 |
| 每格局数 | 20 | 20 |

「布局」指位置、颜色、朝向、槽位这类与难度无关的东西，四档完全相同；「梯度」指次数、数量、序列、演示选择，四档各自抽。

### 3.2 逐任务：四档的差别是怎么做出来的

#### 3.2.1 xhard0 的实际数量：配置数不等于桌上真有多少（2026-09-28 实测）

用户指出「（内环 15）实际生成多少？有一部分取不到的」。读官方 `src/robomme/robomme_env/` 的放置循环，确实有一类任务是**放不下就静默减员**：`VideoUnmask`／`ButtonUnmask`／`VideoUnmaskSwap`／`ButtonUnmaskSwap` 的容器循环 `except RuntimeError: break`（第 i 个 256 次放不下，后面全不放）；`PickHighlight` 的块、`PickXtimes` 的每色块同样 `break`，`PickXtimes` 的目标圆盘失败只记日志；`BinFill` 单块失败跳过继续，且总块配置本来是 `spawn_cubes=[10,12]` 而非固定 12；`PatternLock` 路径长度靠最多 1000 次重抽、仍不合格就用最后一条。其余任务（SwingXtimes、VideoRepick、VideoPlaceButton、VideoPlaceOrder、RouteStick、StopCube、InsertPeg、MoveCube）失败即抛 `SceneGenerationError` 整局重抽，数量精确。

h5 里没有 actor 列表也没有分割图（环境运行时 `obs_mode="rgb+depth+segmentation"`，但录像器落盘只留 RGB／深度），所以按用户原话 20 直接用官方环境实测：`robomme.env_record_wrapper.BenchmarkEnvBuilder(task, dataset="test").make_env_for_episode(ep)` + `env.reset()`（与官方 `evaluation.py` 同路），对 7 个会浮动的任务 × 官方 test 的 hard 12 局（原 episode 3,7,…,47）读 `len(env.unwrapped.spawned_bins)`／`len(all_cubes)`。探针脚本、日志与汇总在 `artifacts/newtask-v7/probe-hard-counts/`（`probe.log` 末行 `PROBE_DONE rows=84 errors=0`、`EXIT_CODE=0`），逐局数值留档 [`docs/validation/newtask-v7/xhard0-placed-counts.md`](docs/validation/newtask-v7/xhard0-placed-counts.md)。预算：7 任务 × 1 档 × 12 局 = 84 次 reset，另加 smoke 时 VideoUnmask 第 3 局重复 2 次，合计 86 次，本机 GPU 1，无轨迹、无录像（原话 20 授权）。

| 任务 | 配置 | 12 局实际放置数 | 结论 |
|---|---|---|---|
| VideoUnmask | 容器 15 | 5,6,6,5,6,4,4,5,6,6,6,6（均值 5.4） | **只放下 4～6 个**，15 是空数字 |
| ButtonUnmask | 容器 15 | 5,5,5,5,4,5,6,6,6,4,6,6（均值 5.3） | 同上，4～6 |
| VideoUnmaskSwap | 容器 4 | 全部 4 | 精确 |
| ButtonUnmaskSwap | 容器 4 | 全部 4 | 精确 |
| PickHighlight | 块 6 | 全部 6 | 精确 |
| PickXtimes | 3 色各 1 块 | 全部 3，圆盘无缺失 | 精确 |
| BinFill | 总块 [10,12] | 10,11,11,11,12,11,10,10,12,12,10,11 | 请求数＝实际数，没有丢块；但总块本来就是 10～12 |

所以真正的断崖在 Unmask 两任务：xhard0 桌上平均 5 个容器，v6 的 xhard1 是 8 内环 + 8 干扰 = 16 个，一步涨到三倍；Swap 两任务是 4 → 8，翻倍。这就是原话 17、18 要修的地方。

#### 3.2.2 定值表（原话 21 附表，逐字；全部定死、无区间；物体数按目视总量等差）

定数规则：①区间一律取上界，xhard0 也取上界作基线；②等差：步长 =（顶档 − xhard0 基线）÷ 4 取整，上界导致某一步偏大时**下调顶档**、不上调低档（低档贴近 xhard0 优先）；③数量类维度按桌面目视总量（内环 + 外环／干扰、目标块 + 干扰块）算，不按外环／干扰单独算；④xhard0 一列写**实测值**（§3.2.1），不是配置数。

| 任务 | 维度 | xhard0 实际 | xhard1 | xhard2 | xhard3 | xhard4 | 步长 |
|---|---|---|---|---|---|---|---|
| VideoUnmask | 桌面容器总数（内环 8 固定 + 干扰） | 5 | 8 + 0 = 8 | 8 + 4 = 12 | 8 + 8 = 16 | 8 + 12 = 20 | +3 / 4 / 4 / 4 |
| | 干扰里藏 cube 数 | — | 0 | 2 | 4 | 6 | 干扰数一半 |
| | pick | 2 | 2 | 3 | 3 | 3 | 上限 3 |
| ButtonUnmask | 同 VideoUnmask | 5 | 8 | 12 | 16 | 20 | 同上（原顶 14 干扰改 12） |
| VideoUnmaskSwap | 容器总数（内环 4 + 外环） | 4 | 4 + 2 = 6 | 4 + 4 = 8 | 4 + 6 = 10 | 4 + 8 = 12 | 2 |
| | swap | 3 | 5 | 7 | 9 | 11 | 2 |
| | pick | 2 | 2 | 3 | 3 | 3 | |
| ButtonUnmaskSwap | 容器总数 | 4 | 6 | 8 | 10 | 12 | 2 |
| | swap | 3 | 3 | 5 | 7 | 9 | 2（xhard1 靠外环 +2 拉开） |
| | pick | 2 | 2 | 3 | 3 | 3 | |
| PickHighlight | 总块 / pick | 6 / 3 | 7 / 4 | 8 / 5 | 9 / 6 | 10 / 7 | 1 / 1 |
| PickXtimes | 桌面块总数（3 色块 + 干扰） | 3 | 4 | 5 | 6 | 7 | 1（需加第 4 干扰色） |
| | 抓取次数 | 5 | 7 | 10 | 12 | 15 | 2～3 |
| SwingXtimes | 桌面块总数 | 3 | 4 | 5 | 6 | 7 | 1 |
| | 摆动轮数 | 3 | 5 | 7 | 9 | 11 | 2 |
| BinFill | 总块 | 10～12 | 12 | 12 | 12 | 12 | 固定 |
| | 投入块数 | 5 | 6 | 7 | 8 | 9 | 1 |
| VideoRepick | 块 / swap / repick | 无锚 | 4 / 4 / 2 | 5 / 6 / 3 | 6 / 8 / 4 | 7 / 10 / 5 | 1 / 2 / 1 |
| PatternLock | 节点数 | 8 | 12 | 16 | 20 | 24 | 4 |
| RouteStick | 段数 | 7 | 10 | 13 | 16 | 19 | 3 |
| VideoPlaceButton | 块数 / 放台次数 | 1 / 2 | 1 / 3 | 1 / 4 | 2 / 5 | 2 / 6 | 1 |
| VideoPlaceOrder | 总放台次数（2 块） | 4 | 5 | 6 | 7 | 8 | 1 |

StopCube／InsertPeg／MoveCube 只有 xhard4，数值不动。

**表的读法（第三次修订补注；上表为原话 21 附表逐字，数值一个不动，只补口径）**：
- 「xhard0 实际」一列混用了两种来源，按来源读：**实测**——Unmask 两任务的 5（12 局实测 VideoUnmask 均值 5.42、ButtonUnmask 5.25、最大 6，取整为 5）、BinFill 总块 10～12、Swap 容器 4、PickHighlight 6、PickXtimes 3；**官方 hard 配置区间上界**（未实测，也不需要实测：这些维度官方代码不会减员）——PickXtimes 抓取 5（`[4,5]`）、SwingXtimes 3、BinFill 投入 5（`[3,5]`）、PatternLock 8（`[4,8]`）、RouteStick 7（`[4,7]`）、VUS／BUS swap 3（`[2,3]`）；**上界、未实测且官方为随机**——VideoPlaceOrder 4（官方 hard 是 `randint(2, len(targets)+1)`，即 2～4，均值 3）。
- 「步长」一列是按表内数值实算的步距：BUS swap 实为 0／2／2／2（xhard0＝xhard1＝3，xhard1 靠外环 +2 拉开）；VU／BU 容器总数为 +3／4／4／4；PickXtimes 抓取为 +2／3／2／3（非严格等差，按上界取整所致）。
- 下文「顶档下调」按条目实数为**八处**（VideoRepick 的 swap 与 repick 分两处计）。

**相对 v6 四档表改了什么**（每处都能对回 `scripts/README.md` 第 3 节的旧值）：
- **Unmask 两任务的贴身环带干扰**：8/10/13/15（VU）、8/10/12/14（BU）→ **0/4/8/12**，两任务相同；含 cube 数从 4/5/[6,7]/… → 0/2/4/6（恒为干扰数一半）。xhard1 干扰取 0：桌上 8 个容器全是候选，只比 xhard0 的 5 个多 3 个、间距更紧，语义与 hard 相同；贴身环带从 xhard2 起加入、每档 +4。若坚持 xhard1 也要有环带则是 2/6/10/14（总数 10/14/18/22），但 xhard1 会跳到两倍，故不取。
- **Swap 两任务外环**：4/6/8/10 → **2/4/6/8**（总数 6/8/10/12，步 2；顶档 14 → 12 个容器）。外环含 cube = 外环数一半 → 1/2/3/4；代码已允许 ≥2 的偶数，不用改规则。swap：VUS [4,5]/[6,7]/[8,9]/[10,12] → 5/7/9/11；BUS 4/5/[6,7]/[8,9] → 3/5/7/9。
- **PickXtimes／SwingXtimes 干扰块**：1/2/3/3 → **1/2/3/4**（顶部不再持平），需要第 4 种干扰色（现只有黄／青／品红，不得与红／蓝／绿目标色相撞）。**第 4 色不加进共用的 `utils/xhard.py::DISTRACTOR_COLORS`**：该三色池同时是四个 Unmask／Swap 任务的干扰色池，`unmask_distractor_sampler.py::parse_distractor_cfg` 要求规格里的 `color_pool` 与它逐字相等、`sample_distractor_layout` 按它的长度 `randperm`，加色会让 v6 的 Unmask／Swap 规格回放全部报错、v7 的随机流整体漂移；改为新增只给 PickXtimes／SwingXtimes 用的 `BLOCK_DISTRACTOR_COLORS`（第二部分 §1.7）。次数：PickXtimes [6,7]/[8,9]/[10,12]/[13,15] → 7/10/12/15；SwingXtimes [4,5]/[6,7]/[8,9]/[10,11] → 5/7/9/11。
- **VideoRepick**：swap [3,4]/[5,6]/[7,8]/[9,12] → 4/6/8/10；repick 2/3/4/[5,6] → 2/3/4/5。
- **PatternLock**：[9,12]/[13,16]/[17,20]/[21,25] → 12/16/20/24（25 格不必占满）。
- **RouteStick**：[8,10]/[11,13]/[14,16]/[17,21] → 10/13/16/19（执行段 50·19 = 950 步，在上限内）。
- **不变**：BinFill 6/7/8/9；PickHighlight 4/5/6/7 与 7/8/9/10；VideoPlaceButton 3/4/5/6（1/1/2/2 块）；VideoPlaceOrder 5/6/7/8；四个 Unmask 的 pick 2/3/3/3。
- **顶档下调共八处**：VU 干扰 15 → 12、BU 14 → 12、Swap 外环 10 → 8、VUS swap 12 → 11、VideoRepick swap 12 → 10 与 repick 6 → 5、PatternLock 25 → 24、RouteStick 21 → 19。代价是 xhard4 比 v6 略容易；反过来保顶档就要放大步长、把 xhard1 推离 xhard0，与原话 17 冲突，故取下调。

#### 3.2.3 逐任务：布局怎么共用、梯度怎么取、低档怎么截

「布局」来自母布局、四档相同；「梯度」按 §3.2.2 定值在环境里现场取；「取前 k 个」只写低档从母布局截前缀的规则。

| 任务 | 四档共用的布局（来自母布局） | 梯度（每档定值；物体数量也是梯度） | 取前 k 个：低档怎么从母布局里截 |
|---|---|---|---|
| BinFill | 按钮位置、托盘偏移、12 个块的颜色／槽位／生成顺序、每色摆放块数 | 投入块数 6 → 7 → 8 → 9（总块固定 12）；**每色投入数按母档嵌套派生**（D-15）：母档 9 块的逐色投入里，按本档随机流逐个去掉 3／2／1 块，得到 xhard1／2／3 的 6／7／8 块 | 不截：12 个块四档全用；投入按上一格的嵌套规则 |
| PickXtimes | 按钮、目标区、3 色目标块、4 个干扰块的位置与颜色 | 抓取次数 7 → 10 → 12 → 15；干扰块数 1 → 2 → 3 → 4 | 干扰块按母布局生成顺序取前 k 个 |
| SwingXtimes | 同 PickXtimes，另加摆动目标点 | 摆动轮数 5 → 7 → 9 → 11；干扰块数 1 → 2 → 3 → 4 | 干扰块取前 k 个 |
| PickHighlight | 按钮、10 个块的位置与颜色 | 总块数 7 → 8 → 9 → 10；pick 数 4 → 5 → 6 → 7；高亮哪几个块每档重抽 | 块取前 k 个 |
| VideoUnmask | 8 个内环容器位置与颜色、12 个干扰容器位置 | 干扰容器数 0 → 4 → 8 → 12；pick 2 → 3 → 3 → 3；干扰里放 cube 的位置每档重抽（数量 0/2/4/6 定死） | 干扰容器取前 k 个（xhard1 取 0 个） |
| ButtonUnmask | 同上，另加按钮位置 | 同上 | 同上 |
| VideoUnmaskSwap | 4 个内环容器位置与颜色、被选目标、发起交换的容器、外环 8 个干扰容器位置与颜色 | 外环干扰数 2 → 4 → 6 → 8；swap 5 → 7 → 9 → 11；pick 2 → 3 → 3 → 3；交换路线与外环块分配每档重抽 | 外环干扰容器取前 k 个 |
| ButtonUnmaskSwap | 同上 | 外环干扰数 2 → 4 → 6 → 8；swap 3 → 5 → 7 → 9；pick 2 → 3 → 3 → 3；交换路线与外环块分配每档重抽 | 外环干扰容器取前 k 个 |
| VideoRepick | 7 个块的位置与颜色（有按钮就含按钮） | 块数 4 → 5 → 6 → 7；swap 4 → 6 → 8 → 10；repick 2 → 3 → 4 → 5；目标块与交换顺序每档重抽 | 块取前 k 个 |
| VideoPlaceButton | 目标区、按钮、块的颜色与位置、放置台位置 | 块数 1 → 1 → 2 → 2；放台次数 3 → 4 → 5 → 6；演示序列、答案每档重抽 | 块取前 k 个；放置台按本档所需台数取前 k 个 |
| VideoPlaceOrder | 同 VideoPlaceButton | 总放台次数 5 → 6 → 7 → 8（四档都是 2 块）；访问顺序、演示、答案每档重抽 | 放置台按本档所需台数取前 k 个 |
| PatternLock | 一条 24 格不重访路径（母布局抽 24 个节点） | 节点数 12 → 16 → 20 → 24 | 取母路径的前 L 个节点（不重访路径的前缀仍不重访） |
| RouteStick | 旋转角、障碍颜色、完整路线（节点与方向） | 段数 10 → 13 → 16 → 19 | 取母路线的前 L 段 |
| StopCube／InsertPeg／MoveCube | 只有 xhard4 | — | — |

两个要点：
- **「取前 k 个」为什么合法**：物体是一个个依次摆的，每个新物体只和已摆好的物体检查距离，所以前 k 个本身就是一组合法摆放。环境里的复核并不覆盖所有任务（PickHighlight 没有复核；随机 bin 的障碍检查发生在注入替换之前），所以不依赖它：阶段 4 派生完成后另跑离线几何闸门 `V7_PREFIX_GEOMETRY`，对每个派生行按本档区域与最小中心距重算一遍（第二部分 §7.6）。
- **梯度为什么不能也从母布局里截**：比如 VideoRepick 的交换计划要依赖块的数量，BinFill 投入块数一变，后面的分配就全变。所以梯度一律在环境里按本档配置重新取；只有布局是注入的。定值后「重新取」退化为取该档唯一的数，序列类（交换路线、演示顺序、高亮 id）仍随档重抽。

### 3.3 最高档 xhard4 和现在是否一致

- **一致的**：代码路径、回注方式和 v6 的 xhard4 相同：先抽签冻结规格，生成与评估时按规格全量回注。StopCube／InsertPeg／MoveCube 仍然只有 xhard4，数值不动。
- **配置数值不再一致**（原话 17～21）：xhard4 有八处顶档下调（§3.2.2「顶档下调共八处」），区间全部定死为上界或等差值。所以 v7 的 xhard4 不是 v6 的 xhard4 换 seed，而是数值也变了的新顶档；v6 xhard4 规格与数值只在 git 历史保留。
- **不一致的**：**具体这 20 局是重新抽的**。seed 从 v6 的 6e6 段换成 v7 的 14e6 段，所以场景和取值都和 v6 的 xhard4 不同，v6 的 xhard4 规格不再发布（git 历史保留）。
- **一个细微差别**：v7 的母布局要同时让 xhard1～3 都派生成功才会入选，派生失败的布局四档一起作废。所以 xhard4 的 20 局是「对低档也可行」的布局，理论上比 v6 的 xhard4 略有筛选偏差。候选作废率会在阶段 4 实测，并写进留档。

## 4. 新的 parity

### 4.1 三侧是什么

| 侧 | 是什么 | 要不要重新生成 |
|---|---|---|
| O | 官方 `1fadc0ec` 的产物 | 不要。已在 A40 上生成过一次，存档后永久复用 |
| P | **打了 tag 的固定锚点 commit** 的产物（不再是「修改前」） | 不要。直接复用这个 commit 当年验证时作为 H 的产物（验证过的 commit 不再验证） |
| H | 当前代码 | 每次改完都重新生成 |

原三档（native）每次都比 O:P、P:H、O:H 三对；v6 xhard 没有 O（官方没有 xhard），只比 P:H；xhard0 这一轮是首次，只有 O:H，`parity-anchor-v7` 起才有 P。锚点不跟着修改走：tag 打上后不再移动，要换锚点就打新 tag。

P 侧产物是锚点 commit 当年**作为 H 生成**的（worker 为 `train_split_worker.run_one`、环境模块属 `robomme_hard`），所以 P 侧的包绑定按登记表记下的生成来源判，不按官方 `_worker` 判（第二部分 §7.7）。

### 4.2 v7 这一轮怎么做

1. 给 `ce3843b4` 打 tag `parity-anchor-v6`。它当年做 v6 OPH 时，P 缓存的两段产物实际生成于 `34a1ceab`（原三档 H，144 局）与 `b1afc804`（v6 xhard H，165 局），到 `ce3843b4` 分别有 15、14 个相关文件差异。打 tag 前逐文件核等价：预审结论是这些差异只涉及 `seed_layout` 移目录后的导入路径、输出目录「已跑过」的判定放宽、bucket 上传白名单修复、比对时补读 `robomme_module`、README 与注释，均不改变 h5 内容；阶段 0′ 按第二部分 §7.7 的判据复核，任何一处涉及生成内容即停下找用户，不打 tag。
2. 实施 v7。
3. 用 v7 的代码再做一次 v6 OPH。O、P 都从公开 bucket 拉回复用，只生成 H：原三档 16 任务 × 3 档 × 3 局 = 144，加上 v6 xhard（xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165）。结果存档。
4. xhard0 生成对拍（第三类，原话 13～15 在原话 6 之外新增）：16 任务 × 1 档 × 12 局 = 192，O:H。
5. v7 自己的正式局生成两次，比对一致性（gen1 对 gen2，(13 任务 × 4 档 + 3 任务 × 1 档) × 20 局 = 1100）。
6. 全部通过后，给 v7 的 commit 打 tag `parity-anchor-v7`，登记 native 144、xhard0 192、v7 1100 三段 P 缓存（v7 段登记 gen1）。以后所有 parity 都以它作 P。

### 4.3 多卡容差：多大、为什么只认 A40

现行容差文件是 `scripts/configs/hard-parity-tolerances.json`，本轮不重标：

| 指标 | 阈值 | 含义 |
|---|---:|---|
| 动作 `action_max_rad` | 0.0413（约 2.4°） | 两侧对应时间步的关节动作最大差 |
| 状态 `state_max` | 0.0411 | 关节与夹爪状态的最大差 |
| 图像 `image_mad` | 1.0 | RGB（0～255）逐像素差的平均值 |
| 帧数 `frames_max` | 5 | 两侧的步数之差 |

**怎么来的**：O、P 两侧各在一台 A40 上生成 144 局，驱动都是 595.71.05，但节点不同。其中 143 对逐字节相同，只有 `PickHighlight/hard/seed 12300` 一对从第 549 步起因 RRT 墙钟噪声分叉，动作差 0.0275。阈值取这个差的 1.5 倍；图像和帧数取下界。

**所以它是「同型号、同驱动、跨节点」的容差，不是跨型号容差**：同一局在本机 RTX 6000 Ada 与 A40 上跑，第 7 步起就全面分叉（关节差 0.029 rad、RGB 逐像素差达 200 以上），这个差异从未进过标定（该探针里型号与驱动大版本同时不同，分叉归因于哪一项没有拆开）。另外它只标定了原三档：用在 v6 xhard 165 与 v7 1100 上属于「未标定外推」，超容差时的分流见第二部分 §4。因此：
- O、P、H 三侧与 v7 的两次生成都必须是 A40 + 驱动 595.71.05；
- P 侧的缓存如果是在不同型号或驱动上生成的，不能复用，必须重新生成；
- 本机 Ada 与 aspen A6000 只做冒烟和静态检查，不产正式对拍数据。

## 5. 两策略评估（SimpleMemVLA 与 FrameSamp+Modulation）

- **评哪两个**：与上一个计划（`docs/plans/0927-robomme-hard-layered-plan.md` §八，留档 `docs/validation/newtask-v6/hard-split/stage6-eval-prep.md`、`stage7-eval.md`）相同：官方 SimpleMemVLA（`checkpoints/simplememvla_robomme`），以及官方 MME-VLA 的 `perceptual-framesamp-modul` 79999（即 FrameSamp + Modulation）。
- **调用方法与上次一致**：沿用上次的两个策略分支、入口与分片脚本（SimpleMemVLA `testhard_eval.py` + `scripts/gl_run_testhard.sh`；MME-VLA `scripts/gl_eval_shard.sh` + `merge_eval_shards.py`），以及上次的去代理、显存 0.75、`--resume` 修复。改动如下（前两处是原计划，后四处是审计补上的必要接线）：
  1. 子模块 gitlink 从 `31e61259` 改为 v7 的 benchmark commit（新切 `PolicyEvalThirdParty-{simplememvla,mmevla}-<MMDD>-<HHMM>`），两个策略仓库也从上次分支再切出新分支 `*-v7-<MMDD>-<HHMM>`，不在旧分支上改（上轮是在评估分支上直接续改；本轮改为另切新分支，旧分支保持上轮结果可复现）。
  2. 打开每局视频回放（见下）。
  3. **按逐身份清单分片**：阶段 8 由 benchmark 侧导出 `artifacts/newtask-v7/eval-identities-1292.jsonl`（每行 `task, episode, tier, seed, candidate`；xhard0 的 `candidate` 记 `null`、另记 `source_episode`），两轮的局集合与 10 片的划分都从这份清单切，两个策略与合并器只认清单，不再各自按「每任务 80 局、每轮每格 10 局」的旧公式算。每轮 646 局不能被 10 整除，片按 v6 实测执行步数估时均衡，不要求每片局数相同。
  4. **绑定核验分两类**：回注局要求 `mode=="replay"` 且 `injected_mismatch==0`；xhard0 局要求 `mode=="export"`、`spec_kind=="native-parity/1"`、`injected_mismatch==0`（xhard0 没有规格可回注，环境里的 `SpecRecorder` 以导出模式运行，`spec_binding` 返回 `available=True`；原计划写的 `available=False` 不成立）。两个策略仓库与合并脚本里「全部局都是 replay」的硬断言相应改成按档分类计数。
  5. **评估步骤的 CPU 数跟着改**：占位 job 改为 4 CPU 后，两个策略脚本里 `srun` 步骤的 `--cpus-per-task` 也改为 4；只改占位 job、步骤仍申请 1 CPU 时，12.226 的 4 CPU 实测不适用。
  6. 策略仓库对 `resolve_episode` 的用法不变：返回 `(seed, tier)`，`TIER_MAX_STEPS["xhard0"]=1300`。
- **xhard0 官方路线对照（原话 13）**：两个策略在 v7 正式两轮之后各加一轮「官方路线」：策略仓库改用官方 `robomme` 包与 `dataset="test"`（即 SimpleMemVLA 上游自带的官方 test 评估入口、MME-VLA 官方 `eval.py` 的 test 分支，不经 `evaluation_hard.py`），只跑每任务 hard 那 12 局（原 episode 号 3,7,…,47），16 任务 × 1 档 × 12 局 = 192，仍切 10 片跑在同一批评估 job 上。准备：两个策略仓库从各自上游官方评估入口另切 `*-official-xhard0-<MMDD>-<HHMM>` 分支，只加一个按 `xhard0_manifest.json` 过滤原 episode 号的开关与视频输出目录，不碰 v7 分支；阶段 9 每策略冒烟 1 局。结果按 `(task, 原 episode 号)` 经清单映射到 seed，与 v7 xhard0 的 192 局对齐，**只报告差异、不作判定**（D-16，§2）。这一轮**只用于对照**，不进 5 档成功率表。
- **评多少**：每个策略评完 v7 全部 1292 局，分两轮，顺序同上次（先 SimpleMemVLA 第一轮 → MME-VLA 第一轮 → 两者第二轮），随后各加一轮官方路线 192 局对照：
  - 第一轮：55 格 × 前 10 局（按 `candidate` 升序）+ xhard0 16 任务 × 前 6 局（按原 episode 号升序）= 550 + 96 = 646；
  - 第二轮：55 格 × 后 10 局 + xhard0 16 任务 × 后 6 局 = 646。
  - 官方路线对照轮：16 任务 × 1 档 × 12 局 = 192。
  - 两策略合计 2 × (1292 + 192) = 2968 局；GL 10 × A40 占位 job，每轮切 10 片。
- **评估占位 job（用户 2026-09-28 定）**：由 agent 自己提交 10 个，规格与上次（`stage6-eval-prep.md`）相同，只把 CPU 从 1 改为 4：`sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:1 --gpu_cmode=shared --cpus-per-task=4 --mem=32G --time=48:00:00 --wrap='sleep infinity'`。依据是 12.226 实测（`ae1cba1e`）：首个请求 1 CPU 约 183 秒、4 CPU 约 61 秒，编译结束后每取一组动作都约 0.22 秒。**模型常驻先不动**，分片与启动方式与上次保持一致（常驻两任务连跑约 3 分 39 秒、分别启动约 6 分钟，只是单次观察，不是三轮完整比较）。生成阶段不另提 job，直接用用户已提交排队的占位 job。数量 10 沿用 12.212 的授权（「eval使用10卡并行」）与原话 11「评估的job你自己提交」；加上 A6 保留的那一个生成席位（阶段 6 结束时按剩余时间选定，不预先钉死为 62126062），评估期间同时在线 11 个，JobID 逐个记入留档，阶段 11 按清单逐个 `scancel`。
- **视频回放：每局都存，落在本机盘 `/data/hongzefu`**：
  - 评估进程把每局 mp4 写到 NFS 暂存目录 `<NFS>/v7-eval-stage/<策略>/<轮>/<片>/`，文件名带 `task_tier_episode_seed`。
  - 本机 sled-vail 另起一个搬运进程（tmux 会话 `v7-vmove-<策略>`），它和评估是两个独立进程：**评估不等搬运，搬运慢了或断了也不影响评估。**
  - 搬运只处理「已完成」的视频。两个策略的终态记录不同名，按策略分别认：SimpleMemVLA 认 `results-shard*.jsonl` 的终态行，MME-VLA 认 `episodes.jsonl` 的终态行（`status` 字段）；视频与记录按 `(task, episode)` 关联，seed 从 `eval-identities-1292.jsonl` 反查后写进目标文件名（MME-VLA 原生文件名不带 seed）；同一局有多行（重评）时取最后一个终态行。再加文件大小 10 秒不变。搬运时 `rsync` 到 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v7/eval-videos/<策略>/<tier>/<task>/`，核对 sha256 一致后删掉 NFS 上的副本。
  - 搬运进程挂了就重启；它只看暂存目录的现状，天然可续。评估结束后再跑一遍全量对账。
  - 本机 `/data` 剩余 5.2T（2026-09-29 `df -h /data`；09-28 为 2.8T，用户已另行释放）。同时驻留的大头：gen1 与 gen2 各约 0.75T（按 v6 xhard 单局均值外推，gen2 在 `PARITY_V7_TWICE` 留档后删）、xhard0 H 侧 192 局、比对时拉回的 O／P 缓存、评估视频。视频大小以冒烟那一局实测外推写进留档；腾空间按 §1 第 9 条 B5 的顺序只删重复缓存与已上 bucket 的内容，不停、不删视频。
  - 搬运慢了或断了不影响评估，但**不能无限积压**：NFS 暂存超过 200G 或搬运停更超过 10 分钟，暂停派发新片，等搬运追上再继续。
- **判定行**（口径同上次）：`EVAL_SMOKE`（每策略 1 局 xhard0 + 1 局 xhard1）、`EVAL_ROUND1`／`EVAL_ROUND2`、`EVAL_IDENTITY_SET episodes=1292`、`EVAL_BINDING=PASS replay=1100 export=192 injected_mismatch=0`（xhard0 局 `mode=export`，其余局 `mode=replay`）、`EVAL_TIER_CAP`，新增 `EVAL_VIDEO=PASS policy=<名> episodes=1292 on_data=1292 sha_bad=0 nfs_left=0`；官方路线对照轮 `EVAL_OFFICIAL_XHARD0=PASS policy=<名> episodes=192 normal=192` 与 `XHARD0_EVAL_PARITY=INFO policy=<名> compared=192 status_diff=<n> steps_diff=<n>`（只报告）。结果按 5 档分表，SimpleMemVLA 与 v6 同档的结果只作参考对照：v7 的布局都换了，不是同一批身份。

## 6. 实施步骤表

| 阶段 | 做什么 | 在哪 | 通过的判据 |
|---|---|---|---|
| 0 准备 | 取回原三档 144 局清单与官方 train 元数据；从官方 test 元数据导出 xhard0 的 192 局清单 `scripts/configs/newtask-v7/xhard0_manifest.json`；写 L／G／N 三表白名单 | 本机 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192` |
| 0′ 定 v6 锚点 | 从公开 bucket 拉回 `O-1fadc0e-a40/native`（144）、`H-34a1cea-a40/native`（144）、`H-b1afc80-a40/xhard`（165），按 bucket 内 `SHA256SUMS` 逐局核 sha；逐文件核 `34a1ceab`／`b1afc804` → `ce3843b4` 的差异不触及生成内容（判据见第二部分 §7.7）；打 tag `parity-anchor-v6` 并推送（等价核验不过则按 §1 第 9 条 B1 打回两个生成 commit）；登记 P 缓存 | 本机 | `ANCHOR_EQUIV=PASS files=15+14 content_affecting=0`；`PARITY_ANCHOR=PASS tag=parity-anchor-v6 cached=144+165 sha_bad=0` |
| 1 改代码：xhard0 与规格模块 | builder 加 xhard0（条目补 `row`／`runtime`）；新 seed 规则；`TIER_MAX_STEPS["xhard0"]=1300`；身份键按 schema 分表；`spec_binding` 新计数；规格根覆盖；runner 加 `test_metadata` 身份来源；`hard_parity.py` 加 `--tier xhard0`／`v7`、目录参数化；`hard_regression.py` 加 `xhard0-reset-parity`／`xhard0-eval-parity`；定向单测；**白名单完整性动态核对**：16 任务 × 1 档 × 1 局 xhard4 导出 + 13 任务 × 3 档 × 1 局派生 = 55 次 reset（本机单 worker，原话 23 批准） | 本机 | `XHARD0_NATIVE=PASS`；`LAYOUT_WHITELIST_COMPLETE=PASS envs=13 unclassified=0 unmatched_patterns=0`；`UPSTREAM_GUARD=PASS`；短测通过 |
| 1′ 改代码：梯度定值 | 按 §3.2.2 改 13 个环境的 `config_xhard1～4`、Unmask 的 `NEWVALUE_DISTRACTOR`（`count=0` 放行）、Swap 的外环数、新增 `BLOCK_DISTRACTOR_COLORS`、五个 `native_blocks` 的 release 分支与 `train_split_config.py::RELEASE_NOTES`；同步改 §1.7 列出的现有单测；单测钉每环境每档配置等于定值表 | 本机 | `V7_TIER_VALUES=PASS envs=13 tiers=4 mismatch=0`；短测通过 |
| 2 改代码：母布局与派生 | derive 信封、L／G／N 分层回注、BinFill 嵌套派生、UnmaskSwap 注入后重规划、四档同步作废与递补、交付集合校验、gen1 交付清单与身份登记；parity 锚点子命令 | 本机 | 无仿真单测通过 |
| 3 冒烟 | 5 任务（BinFill、VideoUnmask、ButtonUnmask、VideoUnmaskSwap、ButtonUnmaskSwap）× 1 布局 × 4 档：reset 5 任务 × (1 母 + 3 派生) = 20、轨迹 5 任务 × 4 档 × 1 局 = 20（原话 23 批准）；xhard0 1 任务 × 1 局 O／H 各生成 1 次（`--dev-smoke`，本机 Ada 只验链路）；第 4 干扰色出图目视 | 本机 | 各任务 `V7_LAYOUT_SHARED`、`V7_RESET_REPLAY` 通过；`NATIVE_SMOKE=PASS tier=xhard0` × 2；`V7_STEP_HEADROOM=INFO` |
| 4 正式抽签与派生 | 16 任务 × 30 候选母布局（VideoPlaceButton、VideoRepick 每任务抽签上限 100，其余 50）；13 任务 × 3 档 × 30 派生；凑不齐 20 局的任务按 §1 第 9 条 B2 追加一轮 30 候选 | GL A40 | `V7_LAYOUT_SHARED=PASS layouts=20 tiers=4`；`V7_PREFIX_GEOMETRY=PASS`；`V7_TIER_FIXED=PASS`；`V7_VISUAL_COUNT=PASS` |
| 5 v6 回归 OPH | 只生成 H：原三档 16 任务 × 3 档 × 3 局 = 144 + v6 xhard (13 任务 × 3 档 + 16 任务 × 1 档) × 3 局 = 165；O、P 用阶段 0′ 拉回的缓存 | GL A40 | `PARITY_O_P`／`P_H`／`O_H=PASS tier=native compared=144`；`PARITY_P_H=PASS tier=xhard compared=165` |
| 5′ xhard0 生成对拍 | O 侧官方 `_worker` + `robomme`（`1fadc0ec` worktree）生成 192；H 侧 `robomme_hard` builder 路线生成 192；O 上传 bucket | GL A40（O、H 两个占位 job） | `GENERATE=PASS side=O tier=xhard0 rows=192`、`GENERATE=PASS side=H tier=xhard0 rows=192`；`PARITY_O_H=PASS tier=xhard0 shape=16x1x12 compared=192 tol_over=0`；`BUCKET_SYNC=PASS side=O tier=xhard0` |
| 6 v7 生成两次 | gen1 (13 任务 × 4 档 + 3 任务 × 1 档) × 20 局 = 1100，产出交付清单并登记身份；gen2 在另一个占位 job 上按清单重放；对拍判定行出来后按 A5 清单逐个 `scancel`，只留剩余时间最长的 1 个（A6） | GL A40（A5 四个占位 job） | `GEN_HOLD_RELEASE=PASS kept=<JobID>`；`V7_DELIVERY_SET=PASS cells=55 per_cell=20 tier_set_equal=13`；`PARITY_V7_TWICE=PASS compared=1100 tol_over=0`（超容差按 B3 分类，`noise` 不计入 `tol_over`，任一 pair 超 5% 停）；`V7_STEP_HEADROOM=PASS`（超 90% 按 B4 上调上限后复判） |
| 7 回放与入口冒烟 | 每格 1 局经评估链回放（(13 任务 × 3 档 + 16 任务 × 1 档) × 1 局 = 55 次 reset）；xhard0 与 xhard1 各起 1 局（2 局，原话 23 批准）；xhard0 reset 层对拍：官方 `robomme` 进程与 `robomme_hard` 进程各 reset 192 局 | 本机 GPU 0 | `V7_RESET_REPLAY=PASS injected_mismatch=0`；`HARD_EVAL_SMOKE=PASS episodes=2`；`XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0` |
| 8 发布与定 v7 锚点 | 替换包内规格、导出 `eval-identities-1292.jsonl`、改 README、留档 `docs/validation/newtask-v7/`；打 tag `parity-anchor-v7` 并登记 | 本机 | `PARITY_ANCHOR=PASS tag=parity-anchor-v7`；`git diff --check` |
| 9 评估准备 | benchmark 切两个 `PolicyEvalThirdParty-*` 分支；两个策略仓库从上次分支切 v7 分支（清单分片、绑定分类、`srun` 4 CPU、视频），另切官方路线分支；自行提交 10 个评估占位 job（每个 4 CPU、32G）；本机起搬运进程；每策略冒烟：v7 路线 2 局（xhard0、xhard1 各 1）+ 官方路线 1 局 | GL A40 + 本机 | `POLICY_DIFF` × 2、`SUBMODULE_PIN`、`EVAL_SMOKE` × 2、`EVAL_OFFICIAL_SMOKE` × 2、冒烟视频已到 `/data` |
| 10 评估两轮 | 每策略 646 + 646（按清单）；边评边搬视频 | GL 10 × A40 | `EVAL_ROUND1/2`、`EVAL_IDENTITY_SET episodes=1292`、`EVAL_BINDING replay=1100 export=192`、`EVAL_TIER_CAP`、`EVAL_VIDEO` × 2 |
| 10′ xhard0 官方路线对照 | 每策略官方 `robomme` + `dataset="test"` 只评 hard 192 局；与阶段 10 的 xhard0 结果按 seed 对齐，只报告差异 | GL 10 × A40 | `EVAL_OFFICIAL_XHARD0=PASS` × 2；`XHARD0_EVAL_PARITY=INFO` × 2 |
| 11 收尾 | 5 档成功率表写入留档；NFS 暂存清空；按清单逐个 `scancel` 10 个评估 job，名下只剩 A6 保留的 1 个占位 job | 本机 | `EVAL_HOLD_RELEASE=PASS remaining_hold=1` |

第二部分 §2 预算全表（含原话 15 为 xhard0 新增的四行、原话 23 追加的四行、原话 24 的「追加候选」行）已一次性批准，阶段 0～11 按表连续执行、不逐阶段等确认（原话 24 A3、A4）。超出预算、判定 FAIL 或触发 §1 第 9 条 B3 的 5% 硬线即停该阶段及其后续并找用户。实施完成后，实测结果以子节追加在本表之后。

### 实施后实测结果（2026-09-29 追加；详细判定行见 `docs/validation/newtask-v7/README.md`）

| 阶段 | 判据 | 实测 |
|---|---|---|
| 0／0′ | `XHARD0_IDENTITY`、`PARITY_ANCHOR tag=parity-anchor-v6` | PASS（16x1x12；cached=144） |
| 1 | `LAYOUT_WHITELIST_COMPLETE` | PASS（unclassified=0，derive_fail=2 只报告） |
| 4 | `V7_LAYOUT_SHARED`／`V7_PREFIX_GEOMETRY`／`V7_TIER_FIXED`／`V7_VISUAL_COUNT` | 全 PASS；母布局 reset 615、派生 1170（ok 1150）；VideoRepick 追加轮（B2） |
| 5／5′ | native 三对、xhard P:H、xhard0 O:H | 全 PASS；xhard0 192 局 sha 全等（2 局两侧都生成失败） |
| 6 | `V7_DELIVERY_SET` | PASS（InsertPeg 追加轮 + 手动补位 2 局，超每格递补上限 10，待用户追认） |
| 6 | `PARITY_V7_TWICE`（H:H2） | **FAIL**：1086 局逐字节相同、13 局噪声；唯一 FAIL 为 InsertPeg/8 第二次生成规划失败，待用户裁决 |
| 7 | `V7_RESET_REPLAY`、`HARD_EVAL_SMOKE`、`XHARD0_RESET_PARITY` | 全 PASS |
| 8 | `V7_STEP_HEADROOM` | 首判超上限 → 按 B4 上调 xhard2／3／4 为 2400／2900／3800，复核 PASS |
| 8 | `PARITY_ANCHOR tag=parity-anchor-v7` | PASS（用户 2026-09-29「1 不挡住 2a」后补打；tag 在生成提交 77fbe70a，cached=144+1100+192 sha_bad=0；native 沿用 v6 锚点缓存） |
| 9 | `SUBMODULE_PIN`、`EVAL_SMOKE` × 2 | PASS（子模块 4a36d505） |
| 10 | `EVAL_ROUND1/2`、`EVAL_IDENTITY_SET`、`EVAL_BINDING`、`EVAL_TIER_CAP` | SimpleMemVLA 全 PASS；MME `EVAL_ROUND1=FAIL`（2 局 error：超长演示、ButtonUnmaskSwap 评估期碰撞检查缺陷），其余 PASS |
| 10′ | `EVAL_OFFICIAL_XHARD0`、`XHARD0_EVAL_PARITY` | PASS；两入口 SimpleMemVLA status_diff=0，MME status_diff=11（50 对 51） |
| 11 | `EVAL_HOLD_RELEASE` | PASS（remaining_hold=1，62268735） |

五档成功率：SimpleMemVLA 141/192、85/260、47/260、33/260、45/320；MME-VLA 51/192、11/260、18/260、12/260、23/320（xhard0～xhard4）。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

R1. `src/robomme/` 零改动（P2）；三个官方入口与录像器零 diff。xhard0 只在 `src/robomme_hard/` 侧新增条目与分派。
R2. 不把 `"xhard0"` 加进 `difficulty.py::NEWVALUE_DIFFICULTIES`／`VALID_DIFFICULTIES`；xhard0 传给 `gym.make` 的 `difficulty` 是 `"hard"`（`normalize_robomme_difficulty` 不认 `"xhard0"`，`spec_kind_for` 据此选原值类别）。
R3. 梯度取值只能等于 §3.2.2 定值表（D-5），每档单点、不留区间；环境侧改动只落 `src/robomme_hard/`（`robomme_hard` 不在 P2 保护范围内，逐文件清单见 §1.7），提取侧改 `scripts/parity/train_split_config.py`。**v6 数值的唯一存放处是包内 v6 规格 header 的 `sampling_config`**：环境类常量就地改成 v7 值后，源码不再能提取 v6 值；v6 规格回注读的是 header（`hard_builder` 取 `header["sampling_config"][env_id]`），不读类常量，所以阶段 5 的 v6 回归不受影响。为留住可复现的 v6 快照，阶段 1′ 先把包内四档 v6 header 的 `sampling_config` 原样冻结到 `scripts/configs/newtask-v6/v6-sampling-frozen.json`（记 sha256）；`test_v6_snapshot_matches_source` 改为「冻结文件 == 包内 v6 header」（阶段 8 换包后改比 `git show ce3843b4:<包内路径>`），不再比源码；新增 `test_v7_snapshot_matches_source`（源码 `release="newtask-v7"` 提取值 == 定值表 == v7 header）。
R4. 派生失败四档同步作废，不许单档换布局；失败不换 seed、不重试到成功；基础设施失败每身份最多重跑 1 次。
R5. 对拍按 D-8／D-11～D-13；O 与已登记的 P 缓存不重新生成，tag 不移动不删除；`--calibrate` 仍只允许 `O:P`，v7 不重标、不改容差文件；两次生成必须同型号同驱动（A40），`generate` 的 A40 断言保留。
R6. reset／轨迹预算按 P3 一次性授权（§2 预算表，用户 2026-09-28 已全表批准，2026-09-29 追加「追加候选」行），乘式写法（P5）；超出任一行上限先停下找用户。
R7. 主会话唯一整合与提交者；子代理只读或按互斥文件集合改动；子代理不 commit、不 push。
R8. `scripts/` 顶层四入口不变（P1）；新脚本落 `scripts/injection-dev/` 与 `scripts/parity/`。
R9. xhard0 对拍的 O 侧只能是 vendor 的官方 `_worker`（`d53f21a7`）+ `robomme`（`1fadc0ec` worktree），进程不得导入 `robomme_hard`（同 R5 口径）；H 侧 `gym.make` 的实参必须取自 `robomme_hard.env_record_wrapper.BenchmarkEnvBuilder(dataset="test-hard")` 的 xhard0 条目，并断言恰为 `{seed, difficulty:"hard"}` 加官方固定四项；两侧 job 的 `episode` 都是原 test episode 号，恢复模式按官方规则、不加 `--no-recovery`。评估层对照同理：官方侧只导入 `robomme`、`dataset="test"`。
R10. **白名单闭世界**：派生与分层回注中，任何 `value()` 路径必须恰好匹配 L（注入）、G（本档现场取值）、N（由母值嵌套派生，D-15）三表之一；都不匹配 → `EpisodeSpecError`，不静默当 G 处理；`record()` 点不进三表。三表中每条模式在阶段 1 的动态核对里至少命中一次，拼错的模式因此暴露（`LAYOUT_WHITELIST_COMPLETE`）。
R11. 共用 `DISTRACTOR_COLORS` 三色池不动（Unmask／Swap 采样器与 v6 规格 header 依赖它逐字相等）；第 4 干扰色只进新常量 `BLOCK_DISTRACTOR_COLORS`。
R12. 不改原三档（easy／medium／hard）任何分支；xhard0 走的正是原 hard 分支，任何「漏改」「顺手统一」都不许碰它。

## 1. 逐文件改动清单

### 1.1 `src/robomme_hard/env_record_wrapper/`

| 文件::锚点 | 改什么 | 关闭态／现有档 | v7 态 |
|---|---|---|---|
| `hard_specs.py::SCHEMA` → `SCHEMAS=("hard-specs/2","hard-specs/3")` | `validate_specs` 按 header schema 分支：`/2` 逻辑原样（读旧快照用），`/3` 增加 v7 校验；**身份键集合按 schema 分表**：`IDENTITY_HEADER_KEYS`／`IDENTITY_ROW_KEYS` 改为 `{"hard-specs/2": 原集合, "hard-specs/3": 原集合 ∪ 新键}`，`identity_sha256` 按行所属 schema 取表，保证 v6 的 `/2` 规格摘要逐字不变 | V6 文件仍可读、`identity_sha256` 不变 | 包内四份为 `/3` |
| `hard_specs.py::SEED_PROFILES` 加 `"v7"`，新增 `V7_SEED_OFFSET=14_000_000`；`seed_rule_for(tier,"v7")` 四档同 offset；`_known_seed_rule` 遍历三族 | — | v6 规则族保持互斥断言 | v7 四档同 seed |
| `hard_specs.py::BUILDER_TIERS=("xhard0",*TIERS)`；`TIERS` 不变 | builder 档序与新值族分开（`TIERS` 被 `EXPECTED_CELLS`、`freeze_specs --tier` 等依赖，只能含四档） | `TIERS` 仍四档 | builder 遍历五档 |
| `hard_specs.py::TIER_MAX_STEPS` 加 `"xhard0": 1300` | — | 四项不变 | 五项 |
| `hard_specs.py::XHARD0_CELLS`（16 任务）、`XHARD0_PER_TASK=12`、`XHARD0_EPISODES=(3,7,…,47)` 只作核对值，筛选仍按 `difficulty=="hard"` | — | — | 断言 12 条／任务 |
| `hard_specs.py` header 新键（只进 `/3` 的身份键表）：`layout_rule={"mode":"shared","parent_tier":"xhard4","whitelist_sha256":…}`；行新键：`layout_parent`（xhard1～3 为 `{"tier":"xhard4","candidate":c,"spec_sha256":…}`，xhard4 为 `null`；全文统一用键名 `spec_sha256`） | `validate_specs` 对 `/3`：四档 seed 同公式；派生行 `layout_parent.spec_sha256` 必须能在 xhard4 文件里找到同 candidate 行（跨文件校验放 `load_specs_v7(root)`，单文件校验只查形态） | — | — |
| `hard_specs.py::spec_binding` | 新增三项：`layout_hit`（本局命中 L／N 表的取值点数，与规格里 `layout_paths_hit` 的条数相等）、`layout_overridden`（其中注入值 ≠ 本档抽到值的条数，只报告：同 seed 下有些点天然相同，如 `BinFill.layout.dynamic`）、`layout_drift`（本档抽到值 ≠ 规格里 `layout_drawn[path]` 的条数，计入 `injected_mismatch`）；xhard0 局照常返回导出模式的 `{available:True, mode:"export", spec_kind:"native-parity/1", injected_mismatch:0}` | 非 layered 规格三项为 0 | 派生局 `layout_hit == len(layout_paths_hit)`、`layout_drift==0`、`injected_mismatch==0` |
| `hard_specs.py::packaged_specs_path`／`hard_builder.py::_tier_specs` | 增加规格根覆盖：环境变量 `ROBOMME_HARD_SPECS_ROOT`（或 builder 构造参数 `specs_root=`），缺省仍读包内；设了覆盖时 `resolve_identity` 多返回 `specs_root` 并打印一行 `SPECS_ROOT=<路径>`，防止误用。阶段 3、7 的回注冒烟与回放在换包（阶段 8）之前靠它读 v7 规格 | 缺省读包内 | 阶段 3／7 指向 `artifacts/newtask-v7/…` |
| `hard_builder.py::_xhard0_entries(env_id)` 新增 | `__init__` 现在在 `super().__init__` 之后立刻清空 `metadata_index`，改为先取出 `dataset="test"` 的 hard 子集再清空；筛 `difficulty=="hard"`，按原 episode 升序；与 `scripts/configs/newtask-v7/xhard0_manifest.json` 双向核对（源文件 sha256、12 条、seed 唯一）；读到 0 条或传了元数据覆盖路径时直接报错 | — | 条目 `{tier:"xhard0", row:{seed, candidate:None, source_episode}, runtime:{difficulty:"hard"}, sampling_config:None, spec:None}`——补 `row`／`runtime` 两键，使 `resolve_episode`、`_entry`、`resolve_identity`、`_hard_env_kwargs` 的现有读法不 KeyError |
| `hard_builder.py::_test_hard_entries` | 先 xhard0 12 条，再 `for tier in TIERS` 原逻辑；每格断言 `delivery_per_cell==20` | — | 92／32 局 |
| `hard_builder.py::_hard_env_kwargs` | `tier=="xhard0"` 分支放在读 `entry["runtime"]` 之前，只返回 `seed, difficulty="hard"`；其余分支不变 | — | — |
| `hard_builder.py::resolve_episode`／`_entry` | xhard0 条目按上面的 `row` 形态读 seed；无仿真单测覆盖 `resolve_episode(0..11)` 与 `(12..)` | — | — |
| `hard_builder.py::resolve_identity` | xhard0 返回 `{episode, tier:"xhard0", source_dataset:"test", source_episode, seed, spec_sha256:None, source_run:None}`；派生行多返回 `layout_parent` | — | — |
| `__init__.py` | 导出 `BUILDER_TIERS` | — | — |

### 1.2 `src/robomme_hard/robomme_env/utils/episode_spec.py`

**接线方式（定）**：母规格与白名单装进 `native_episode_spec` 的 **derive 信封**传入，由 `SpecRecorder.__init__` 拆包；16 个环境类 `__init__` 里 `SpecRecorder(native_episode_spec, "<Task>", {"seed": seed}, difficulty=...)` 的调用一行不改，`gym.make` 也不新增 kwarg（ManiSkill `BaseEnv` 不收未知参数，原计划的 `native_layout_parent=` 无处接收）。PickXtimes／SwingXtimes 在 `__init__` 里就取 `objects.num_repeats`，信封方式在构造时即进入 derive 模式，不存在「构造后再切换」的时序问题。

| 锚点 | 改什么 |
|---|---|
| `SPEC_KIND_LAYERED="native-layered/3"`，`SPEC_KINDS` 加入 | 派生规格类别 |
| `SpecRecorder.__init__(spec, task, identity=None, difficulty=None)` | **签名不变**。新增分支：`spec.get("envelope")=="derive"` → `mode="derive"`，从信封取 `parent`（母规格，`spec_kind` 须为 `native-newvalue/2`、`task` 相同）与 `layout`（本任务的 L／G／N 三表）；`spec["spec_kind"]=="native-layered/3"` → `mode="replay"` 且 `layered=True`。**接受集合**：`spec_kind_for(difficulty)=="native-newvalue/2"` 时接受 `{native-newvalue/2, native-layered/3}`，原值难度只接受 `native-parity/1`，「原值与新值规格不许互喂」的检查保留。对外暴露只读属性 `layered`（供 §1.8 的采样器判断） |
| `SpecRecorder.value` | 路径先按 R10 分类（L／G／N，都不命中即抛错）。`derive`：L → 照常抽一次（随机流不漂移），记 `layout_drawn[path]=drawn`，返回母值（列表值返回 `parent[:len(drawn)]`，母值比抽到的短即抛错；母规格缺该路径即抛错）；N → 照常抽一次，记 `layout_drawn`，返回 §1.8 的嵌套派生值；G → 照常抽、照常用。`replay` 且 `layered`：L／N → 比对对象为 `spec["layout_drawn"][path]`（**逐位相等**：同代码同 seed 的 CPU 随机流是确定的，不用浮点容差），使用值为冻结值；G → 原逻辑 |
| `SpecRecorder.to_dict` | layered 导出多写 `layout_parent`、`layout_drawn`、`layout_paths_hit`（命中 L／N 的路径集合） |
| `leaf_paths`／`consumed_paths`／`unused` | 不变。派生规格只含本局实际使用值，母规格多出的逐项路径（如 xhard4 的第 4 个干扰块）**不进派生规格**，所以派生局回注时 `unused==0`；「多出的自动 unused」只描述派生运行中母规格一侧，不计入派生局的 `unused` |

### 1.3 布局白名单（写成 `src/robomme_hard/env_metadata/test-hard/layout_whitelist.json`，随包发布，sha 进 header）

**匹配语义（定）**：JSON 里每个环境三个列表 `L`／`G`／`N`，元素是模式字符串。精确路径逐字匹配；以 `.*` 结尾的模式匹配「该前缀 + `.` + 任意一段」（如 `layout.cubes.*` 匹配 `layout.cubes.3`，不匹配更深层）；以 `[:n]` 结尾的模式只匹配去掉后缀后的精确路径，并声明该值是列表、按本档抽到的长度取母值前缀。下表是静态审计的初稿，**以阶段 1 `LAYOUT_WHITELIST_COMPLETE` 的动态结果为准**：每个环境跑 1 局 xhard4 导出 + 13 个梯度环境各 3 档派生，trace 里每条 `value()` 路径必须恰好匹配一个模式，每个模式至少命中一次；只在低档出现的取值点（如 VideoPlaceOrder 只在 xhard1／3 抽的 `count_order`）也由派生那 39 局覆盖到。

| 环境 | L（注入；`*` 为逐项路径，`[:n]` 为列表按抽到长度取前缀） | G（现场重抽）；N 另注 |
|---|---|---|
| PickXtimes | `layout.button_xy`、`objects.color_order`、`objects.target_color_idx`、`layout.goal_xy`、`layout.cubes.*`、`objects.target_cube_idx`、`layout.distractors.*` | `objects.num_repeats` |
| SwingXtimes | 同上，另 `layout.targets.*` | `objects.num_repeats` |
| BinFill | `layout.dynamic`、`layout.button_xy`、`layout.board.offsets`、`objects.color_pool`、`objects.put_in_color`、`objects.spawn_numbers`、`objects.spawn_order`、`layout.slots.*`、`objects.slot_assignment`、`initializations.*.color_order` | **N**：`objects.target_numbers`（D-15 嵌套派生，§1.8） |
| VideoUnmaskSwap／ButtonUnmaskSwap | `layout.type_choice`、`layout.bins.*`、`objects.color_order`、`objects.selected`、`objects.target_choice`、`objects.swap_initiator_indices`、`objects.swap_initiator_third`、`objects.distractors.bins.*`、`objects.distractors.color_order` | `objects.n_swaps`、`objects.n_picks`、`objects.swap_plan_seed`、`actions.swap_pairs.*`、`objects.distractors.cube_count`、`objects.distractors.cube_bins`、`objects.distractors.label_perm`、`objects.distractors.swap_plan_seed`、`objects.distractors.swap_order`（原稿漏列） |
| VideoUnmask／ButtonUnmask | `layout.button_xy`（BU）、`layout.bins.*`、`objects.color_order`、`objects.distractors.bins.*`、`objects.distractors.color_order` | `objects.distractors.cube_count`、`objects.distractors.cube_bins`、`actions.sampling_trace.constructor_draw`（BU） |
| VideoRepick | `objects.color_rgb`、`layout.cubes.*`（按钮不是取值点，规格里没有 `layout.button_xy`，按钮位置随块布局确定） | `objects.num_repeats`、`objects.n_swaps`、`objects.target`、`objects.swap_initiators_remaining`、`objects.swap_plan_seed`、`actions.swap_pairs.*` |
| VideoPlaceButton | `layout.goal_xy`、`layout.button_xy`、`objects.color_order`、`layout.cubes.*`、`layout.targets.*` | `objects.demo_ids`、`objects.swap_pair_ids`、`objects.task_flag`、`objects.answer_demo_index`、`objects.extra_place_owner_ids`、`objects.extra_place_target_ids.*` |
| VideoPlaceOrder | 同 VideoPlaceButton 的 L | `objects.visit_counts_by_object`、`objects.demo_ids`、`objects.swap_pair_ids`、`objects.visit_ids_by_object.*`、`objects.answer_demo_index`、`objects.which_in_subset`、`objects.button_after_visit_index` |
| PickHighlight | `layout.button_xy`、`objects.color_rgba.*`、`layout.cubes.*` | `objects.n_cubes`、`objects.highlight_count`、`objects.highlight_ids` |
| PatternLock | `actions.path_nodes[:n]` | （无） |
| RouteStick | `layout.rotation_deg`、`layout.obstacle_rgb.*`、`actions.nodes[:n]`、`actions.directions.*` | `objects.L` |
| StopCube／InsertPeg／MoveCube | 不派生（只有 xhard4） | — |

上表各格中的对象描述（如 SwingXtimes 的 `layout.targets.*`、VideoPlaceButton「块取前 k 个」、VideoPlaceOrder「放置台取前 k 个」）以阶段 1 的 trace 为准修订，第一部分 §3.2.3 同步改。记录点一律不进三表。

### 1.4 `scripts/injection-dev/`

| 文件::锚点 | 改什么 |
|---|---|
| `freeze_specs.py::main` | 加 `--seed-profile {v6,v7}`（默认 v7）、`--select` 支持 `0..19` 区间写法；`--tier xhard4 --candidates-per-env 30 --select 0..19`；header 写 `layout_rule`；VideoPlaceButton、VideoRepick 用现有 `--task-max-reset-attempts` 设为每任务 100（D-17），其余沿用 `--max-reset-attempts 50`。`--select 0..19` 只是初选：xhard4 文件保留全部 30 个候选行，最终交付哪 20 个由候选池状态决定（见 `_rollout.py` 行）；MoveCube 的 `stratified_select` 先取每种运动方式编号最小的候选再补齐，所以它的初选不等于编号 0..19，验收只核 `delivery_per_cell=20` 与选中数，不按编号写死 |
| `_draw.py::draw_task`／`merge_task_rows` | 传 v7 规则；其余不变 |
| `_freeze.py::freeze` | `/3` 封签；`delivery_per_cell=len(select)=20`；MoveCube 的 `stratified_select` 只对 xhard4 生效（不变） |
| 新增 `derive_specs.py` | 输入 xhard4 v7 文件 + 白名单 + 目标档；对每个候选起环境 `gym.make(task, sampling_config=cfg[tier], native_episode_spec={"envelope":"derive","parent":母规格,"layout":白名单[task]}, seed=母 seed, difficulty=tier)`（§1.2 derive 信封）→ `reset` → 导出派生规格 → 按目标档 header 封签写 `xhard{1..3}/specs.jsonl`；派生失败只写进 `derive-report.json`（`derive_fail` 逐候选原因），**规格文件在冻结后不再改写**，四档同步作废由候选池表达（下一行）；启动前断言 `robomme_failure_recovery` 未开；多 worker、`--workers`、`--gpus`、`--dry-run` 打印 reset 预算 |
| `_rollout.py::plan_pending`／`apply_results` | 新增候选池文件 `v7-candidate-pool.json`（单写者、目录锁），是每个 `(task, candidate)` 状态的唯一真源：`derive_ok`（四档规格齐全）→ `selected` → 各档 `tried`／`delivered`／`failed`。某档某候选 rollout 失败 → 该候选在该任务所有档一起退选，按候选号递补下一个 `derive_ok` 且各档均未 `tried` 的候选；**只有 xhard4 的三个任务**（StopCube／InsertPeg／MoveCube）的递补条件只看 xhard4 一档。每格递补上限 10（§2）。收尾写 `delivery.json`：每行 `task, tier, candidate, seed, episode, spec_sha256, h5_sha256, frames`，并断言每任务各档交付的候选集合相同（`V7_DELIVERY_SET`） |
| `generate_h5.py` | `--mode continue` 的现有参数 `--specs` 扩成可接收 v7 规格根目录（四档一起，读候选池）；`--mode replay` 的 `--specs` 由「缺省读包内」扩成可显式指定规格根（gen2 用）；非 `--dev-smoke` 时与 `hard_parity.py generate` 同样断言 A40，并把 GPU 型号、驱动、`src_commit` 写进 launch 记录。gen1 与 gen2 的身份登记与比对一律经 `hard_parity.py`（§1.5），不直接用本脚本的产出做比对 |
| `_report.py` | 报告增加 `derive_fail`、`sync_dropped` 计数（显式零值） |
| 删除 `migrate_smvla_specs.py` | 见 §7.5；随之成为死代码的 `freeze_equiv` 与 S4 常量一并删除 |
| `site/v6_tier_monotone.py` | 加 `--specs-root` 读 v7 四档实际值；`--fixed` 的语义见 §1.7 |

### 1.5 `scripts/parity/`

| 文件::锚点 | 改什么 |
|---|---|
| `train_split_worker.py::run_one` | 生成时**只回注冻结规格**（xhard4 为 `native-newvalue/2`，xhard1～3 为 `native-layered/3`），不在 worker 里派生——派生只发生在阶段 4 的 `derive_specs.py`；`spec_replay.json` 多写 `layout_hit`／`layout_overridden`／`layout_drift` |
| `train_split_runner.py` | `--identity-source` 加第三种 `test_metadata`：按 `<src-root>/src/robomme/env_metadata/test/*.json` 的 hard 子集逐条核 seed 与 difficulty，并与 `xhard0_manifest.json` 双向核对（现有 `train_metadata` 会把 test 身份判为不符而退出，`formula` 需要 `attempt` 也不适用）；`formula` 接受 v7 规则 |
| `hard_parity.py`（锚点机制） | 新增 `anchor` 子命令（`register --tag --h5-root` 写 `docs/validation/parity-anchors.json`、`check --tag` 输出 `PARITY_ANCHOR`）；`compare` 的 P 侧改为 `--p-anchor <tag>` 从登记表取目录并先跑 `check`；`--calibrate` 仍只许 O:P |
| `hard_parity.py`（xhard0） | `TIERS` 加 `"xhard0"`：清单 `scripts/configs/newtask-v7/xhard0_manifest.json`（schema `train-parity-manifest/1` 同形，`source_ref=1fadc0ec`，行 `{task, episode:原 test 号, seed, difficulty:"hard"}`，由 `src/robomme/env_metadata/test/*.json` 的 `difficulty=="hard"` 记录导出并记源文件 sha256）；`rows_for("xhard0")` 走 `native_rows`，身份键仍 `(task,"hard",seed)`；`cmd_generate --tier xhard0`：走 native 分支（条件由 `args.tier == "native"` 改为 `in ("native","xhard0")`），并给 runner 传 `--identity-source test_metadata`；O 侧与 native 完全相同（`official._worker`，`ROBOMME_ENV_PACKAGE=robomme`），H 侧在 native 的 `--force-mirror` 之上多传 `--builder-route test-hard`；`cmd_compare --tier xhard0` 的 `shape` 文案 `16x1x12`；`publish --side O --tier xhard0` 段名 `O-1fadc0e-a40/xhard0` |
| `train_split_worker.py::run_one`（xhard0） | payload 第 5 项可选 `builder_route`（runner 传 `(job, None, None, False, "test-hard")`，第 4 项 `disable_recovery` 占位为 `False`）：为 `"test-hard"` 时导入 `robomme_hard.env_record_wrapper.BenchmarkEnvBuilder(job.task, dataset="test-hard")`，按 seed 在 `resolve_identity` 里找到 `tier=="xhard0"` 的 episode 号，取 `_hard_env_kwargs(ep)`，断言其键集合恰为 `{seed, difficulty}` 且值等于 job；把结果并入 `kwargs` 后其余逐字沿用官方 `_worker`；`binding` 多写 `builder_route`、`builder_episode`、`builder_tier`、`recovery_mode`；`hard_parity.py::Mover.handle` 写 `identities.jsonl` 的固定字段表同步加这四项 |
| `train_split_runner.py` | 透传 `--builder-route {test-hard}`；与 `ROBOMME_ENV_PACKAGE=robomme` 同用时直接报错（R9） |
| `hard_regression.py::xhard0-reset-parity` 新增 | 每任务起两个 spawn 子进程：官方侧只导入 `robomme`（`BenchmarkEnvBuilder(task, dataset="test")`，12 个 hard 原 episode 号），`robomme_hard` 侧 `dataset="test-hard"` episode 0～11；两侧 `make_env_for_episode(ep)` 的 `include_*` 标志与 `max_steps` 相同（先断言两侧 obs 键集合相同）。**分层比对（D-16）**：确定性层——两侧 `gym.make` 实参与包装链类名序列、底层 `env.unwrapped` 在演示回放开始前的 `get_state_dict()`、seed、`task_goal`、多选项列表逐位相等（`np.array_equal`），不等即 FAIL；演示层——演示帧数、演示帧、演示后状态与 `reset` 返回的 obs 只报告差异（RRT 墙钟噪声）。输出 `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0 first_det_diff=-` 与 `XHARD0_DEMO_DIFF=INFO frames_equal=<n> max_frame_diff=<n>` |
| `hard_regression.py::xhard0-eval-parity` 新增 | 只报告（D-16）。输入官方路线的终态记录（按策略：SimpleMemVLA `results-shard*.jsonl`、MME-VLA `episodes.jsonl`；键 `task, episode:原 test 号`，终态在 `status`）与 v7 评估记录（`task, tier=="xhard0", identity.seed, status, steps`）；官方侧经 `xhard0_manifest.json` 把原 episode 号映射到 seed，按 `(task, seed)` 对齐，缺失或多余即报错（这是数据完整性，不是一致性判定）；输出 `XHARD0_EVAL_PARITY=INFO policy=<名> compared=192 status_diff=<n> steps_diff=<n>` 与逐局差异表 |
| `hard_parity.py` | `SIDES` 加 `H2`，`PAIRS` 加 `H:H2`，`TIERS` 加 `"v7"` 与 `"xhard0"`（v7 清单即 gen1 的 `delivery.json`，行键 `task/tier/candidate/seed/episode`，`xhard_rows` 同时接受 `tier` 与 `difficulty`）；`cmd_generate --tier v7 --side H2` 走 `generate_h5.py --mode replay --identities <delivery.json> --specs <v7 规格根>`，与 H 侧同样过 A40 断言、写 launch、`identities.jsonl`、`SHIPPED`；新增 `import-delivery` 子命令把 gen1 的 `delivery.json` 与逐局 h5 登记成 H 侧 `identities.jsonl`（sha 重算核对，接替被删的 `cmd_import_s4`）；`LOCAL_H5_ROOT`／`COMPARE_ROOT` 默认改到 `artifacts/newtask-v7/parity/{h5,compare}`，`compare`／`publish`／`binding` 加 `--h5-root`／`--compare-root` 参数，比对目录已存在时加 `--run-name` 另起子目录而不是拒绝；`compare` 先核两侧 `recovery_mode` 逐局相等；`compare` 的 `both_success == n` 条件改为：两侧同因规划失败的局单列为 `both_fail=<n>`、按 `success_equal` 计入，不直接判 FAIL，`both_fail>0` 时判定行附原因表交用户裁决；`cmd_generate --tier native` 透传 `--metadata-root scripts/configs/newtask-v3/official_train`（取回后）；`cmd_compare` 的 `shape` 文案按 tier 取：native `16x3x3`、v7 `13x3x20+16x1x20`；`_binding_ok` 对 `H2` 与 `H` 同规则；`cmd_import_s4` 删除 |
| `hard_regression.py` | `s4-subset` 删除；`reset-replay` 加 `--specs-root`（阶段 7 在换包前读 v7 规格），从 v7 四档每格取 candidate 最小的正式局（55 局）经评估链回放，判定 `V7_RESET_REPLAY`；新增 `layout-shared`（静态，`V7_LAYOUT_SHARED`，含反向核对）与 `prefix-geometry`（静态，`V7_PREFIX_GEOMETRY`）；`eval-smoke` 的局数断言改 `32 if XHARD4_ONLY else 92`，episode 0 为 xhard0 时断言 `mode=="export"` 与 `spec_kind=="native-parity/1"`，episode 12 为回注局时断言 `mode=="replay"` |
| `scripts/configs/newtask-v3/` | 从 `6e70c0bf` 取回 `subset_manifest.json` 与 `official_train/`（只读清单，不再删除；P1 只约束 `scripts/` 顶层文件，不约束子目录内容） |
| `scripts/configs/newtask-v6/v6-sampling-frozen.json` 新增 | 阶段 1′ 从包内四档 v6 规格 header 原样取出 `sampling_config`（R3） |
| `scripts/configs/newtask-v7/xhard0_manifest.json` 新增 | 阶段 0 由 `hard_parity.py export-xhard0-manifest` 从官方 test 元数据导出（只读 `src/robomme/`），16 × 12 = 192 行，记 16 份源文件 sha256；`_xhard0_entries` 与本清单双向核对 → `XHARD0_IDENTITY` |

### 1.6 `scripts/evaluation_hard.py`、README 与测试

- `evaluation_hard.py`：不改逻辑；`diff scripts/evaluation.py scripts/evaluation_hard.py` 仍恰好 README 第 1 节那 4 处。
- README 三份（`scripts/README.md`、`src/robomme_hard/README.md`、`scripts/parity/README.md`）按第一部分 §4 改数字与链路说明；`readme.md` 不动。
- 测试：新增 `tests/lightweight/test_xhard0_native.py`（身份 16×1×12、分派实参、`TIER_MAX_STEPS` 五项）、`test_v7_layout_shared.py`（白名单形态、`derive`／layered 回注在无仿真夹具下的 `layout_hit`／`layout_overridden`／`layout_drift` 行为、四档同步递补状态机）、`test_v7_seed_rule.py`（v7 四档同 seed、与 v5/v6 段互不重叠）；改 `test_v6_difficulty_tiers.py::test_v6_seed_rule_offsets_disjoint` 限定 v6 族；`test_hard_state_machine.py` 参数化 v6/v7；`test_hard_parity.py` 补 `H:H2`／`v7`／`xhard0`（清单导出、`shape=16x1x12`、H 侧 `--builder-route` 断言、R9 互斥）用例；`test_train_split_parity.py` 补 worker `builder_route` 夹具（假 builder 返回非 `{seed, difficulty}` 键集合时必须抛错）；`test_wrapper_chain.py`（gpu）对 test-hard episode 0（xhard0）与 episode 12（xhard1）各做一次；新增 `test_v7_whitelist_semantics.py`（`.*`／`[:n]` 匹配、三表互斥、未分类路径抛错）、`test_v7_binfill_nested.py`（嵌套派生恒满足 `target_i ≤ 母 target_i`、总数 6／7／8、同 seed 可复现）、`test_v7_candidate_pool.py`（同步退选与递补、只有 xhard4 的任务、交付集合断言）、`test_hard_builder_xhard0.py`（`resolve_episode(0..11)` 不 KeyError、`_hard_env_kwargs` 恰为 `{seed, difficulty}`）；需改的现有单测见 §1.7 末行。

### 1.7 梯度定值（§3.2.2）的逐文件落点（环境侧在 `src/robomme_hard/`，提取与工具在 `scripts/`）

| 文件::锚点 | 现值（v6） | v7 定值 |
|---|---|---|
| `robomme_env/VideoUnmask.py::NEWVALUE_DISTRACTOR` | xhard1 `(8,[4,4])`、xhard2 `(10,[5,5])`、xhard3 `(13,[6,7])`、xhard4 `XHARD_DISTRACTOR`(15) | xhard1 `(0,[0,0])`、xhard2 `(4,[2,2])`、xhard3 `(8,[4,4])`、xhard4 改为 `_newvalue_distractor(12,[6,6])`（现在 xhard4 与 `XHARD_DISTRACTOR` 是同一个对象，改的是 `NEWVALUE_DISTRACTOR["xhard4"]` 这一项，`V5_DISTRACTOR_PRESETS` 预设不动）；`config_xhard*` 的 `bin=8`、`pick=2/3/3/3` 不变 |
| `robomme_env/ButtonUnmask.py::NEWVALUE_DISTRACTOR` | xhard3 `(12,[6,6])`、xhard4 14 | 同 VideoUnmask：`(0,[0,0])`／`(4,[2,2])`／`(8,[4,4])`／`(12,[6,6])` |
| `utils/unmask_distractor_sampler.py::parse_distractor_cfg` | `if count < 1: raise ValueError` | 放宽为 `count < 0` 才报错（xhard1 的硬阻塞）；其余路径已核过可走空列表：`sample_distractor_layout` 的 `randperm(0)`、`verify_distractor_layout` 的 0／0／0、停放与误抓判定。count=0 时规格里没有 `objects.distractors.bins.*` 键，`V7_VISUAL_COUNT` 改读恒有记录的 `objects.distractors.placed` |
| `robomme_env/VideoUnmaskSwap.py`／`ButtonUnmaskSwap.py::v6_distractor_cfg(task, 2 + 2 * newvalue_tier(tier))` | 外环 4/6/8/10 | `2 * newvalue_tier(tier)` → 2/4/6/8；`cube_count_range=[count//2]*2` 不变 |
| `VideoUnmaskSwap.py::config_xhard1～4` | swap `[4,5]/[6,7]/[8,9]/[10,12]`，pick 2/3/3/3 | `swap_min==swap_max` = 5/7/9/11；pick 不变 |
| `ButtonUnmaskSwap.py::config_xhard1～4` | swap `4/5/[6,7]/[8,9]` | 3/5/7/9 |
| `robomme_env/PickXtimes.py` 档位表 | 次数 `[6,7]/[8,9]/[10,12]/[13,15]`，干扰 1/2/3/3 | `number_min==number_max` = 7/10/12/15；干扰 1/2/3/4 |
| `utils/xhard.py` 新增 `BLOCK_DISTRACTOR_COLORS = DISTRACTOR_COLORS + (第 4 色,)` | `DISTRACTOR_COLORS` 黄／青／品红 3 色（Unmask／Swap 共用，R11 不动） | PickXtimes、SwingXtimes 的 `_newvalue_decision`、`XHARD_DECISION`（`_native_decision` 用它，不是 `NEWVALUE_DECISION["xhard4"]`，两处同步）、`palette` 三处改用新常量；第 4 色候选：橙 `(1,0.5,0,1)` 离红色目标块过近，备选白 `(0.95,0.95,0.95,1)`、棕 `(0.55,0.35,0.15,1)`、灰 `(0.5,0.5,0.5,1)`，阶段 3 出图目视选定（须与红／蓝／绿目标色及 PickHighlight 高亮色可分） |
| `robomme_env/SwingXtimes.py` 档位表 | 轮数 `[4,5]/[6,7]/[8,9]/[10,11]`，干扰 1/2/3/3 | 5/7/9/11；干扰 1/2/3/4 |
| `robomme_env/VideoRepick.py::config_xhard*` | swap `[3,4]/[5,6]/[7,8]/[9,12]`，repick `2/3/4/[5,6]`（repick 用 `num_repeats_low`／`num_repeats_high_exclusive` 表示，xhard4 为 `(5,7)`） | swap 4/6/8/10；repick 2/3/4/5（xhard4 改为 `(5,6)`）；块 4/5/6/7 不变 |
| `robomme_env/PatternLock.py::config_xhard*` | `[9,12]/[13,16]/[17,20]/[21,25]` | `[12,12]/[16,16]/[20,20]/[24,24]` |
| `robomme_env/RouteStick.py::config_xhard*` | `[8,10]/[11,13]/[14,16]/[17,21]` | `[10,10]/[13,13]/[16,16]/[19,19]` |
| BinFill、PickHighlight、VideoPlaceButton、VideoPlaceOrder、StopCube、InsertPeg、MoveCube | 已是定值 | 不动 |
| `scripts/injection-dev/_extract.py::build_sampling`（薄封装）与 `scripts/parity/train_split_config.py::RELEASE_NOTES`／`extract_task` | 只认到 `newtask-v6`；13 个环境里只有 VideoUnmaskSwap、ButtonUnmaskSwap、VideoRepick、VideoPlaceOrder、VideoPlaceButton 五个的 `native_blocks` 带 `release` 形参，其中四个对未知 release 直接 `raise` | `RELEASE_NOTES` 加 `newtask-v7`；上述五个 `native_blocks` 的 release 分支加 `newtask-v7`（取当前类常量，即 v7 值）；其余 8 个没有 release 形参的环境直接返回当前常量。v6 值不再从源码提取（R3） |
| `scripts/injection-dev/site/v6_tier_monotone.py` | `check_chain` 从 `hard` 起，每步「无维度下降、至少一维严格上升」，否则 `flat_step` | 加 `--fixed`，语义写死为「每档实际值等于定值 + 相邻档无维度下降 + 每步至少一维上升」（原稿「按档严格递增」逐维不成立：Unmask 的 pick 2/3/3/3、VideoPlaceButton 块数 1/1/2/2）；`PLAN_TIERS` 的 v7 版给 VideoUnmask／ButtonUnmask 加「桌面容器总数」维度（hard=5，之后 8／12／16／20），否则 hard→xhard1 两维都持平、必报 `flat_step` → `V7_TIER_FIXED` |
| `scripts/injection-dev/site/v6_candidate_values.py` | 档位取值表写死 v6 区间 | 加 v7 定值表分支 |
| 测试 | `test_v6_snapshot_matches_source` | 新增 `tests/lightweight/test_v7_tier_values.py`：13 环境 × 4 档配置逐项等于 §3.2.2 → `V7_TIER_VALUES`。**逐档钉死 v6 值、就地改后必 FAIL、须同步改为 v7 值的现有单测**：`test_v4_xhard_pickxtimes.py`、`test_v4_xhard_swingxtimes.py`、`test_v4_xhard_unmaskswap.py`、`test_v4_xhard_videorepick.py`、`test_v5_xhard_patternlock_routestick.py`、`test_v6_swap_uniform.py`（含 `outer_count = 2 + 2*index`）、`test_v6_difficulty_tiers.py`、`test_v4_decision_guard.py`、`test_v6_tier_monotone.py`（`test_final_plan_table_passes`、`test_button_unmask_plan_matches_approved_snapshot`）、`test_v5_xhard_videounmask_buttonunmask.py`、`test_v6_candidate_values.py`；`test_v5_unmask_distractor_sampler.py`、`test_xhard_utils.py` 钉的是三色池，按 R11 保持不动 |
| 文档 | `scripts/README.md` 第 3 节、`src/robomme_hard/README.md` ② 的四档表 | 改成五档定值表（xhard0 列写实测放置数与配置数两项），旧表移入历史小节 |


### 1.8 共用布局的运行时修补（审计后新增；环境侧，均在 `src/robomme_hard/`）

| 文件::锚点 | 问题（审计实证） | 改法 |
|---|---|---|
| `robomme_env/BinFill.py::_load_scene`（`objects.target_numbers` 取值点）与 `_initialize_episode` | 母布局的逐色摆放数满足 `spawn_i = max(target_i, 1)` 再补足；低档若独立重抽逐色投入，某色投入超过母布局摆放数时 `_initialize_episode` 的 `len(cube_collection) < target_number` 抛 `SceneGenerationError`，按包内 30 条 xhard4 候选估算三档联合存活约 28% | **D-15 嵌套派生**：该点归 N 表。derive 与 layered 回注时照常抽一次（保持环境随机流不变、记 `layout_drawn`），实际使用值由母 target 向量嵌套得到——把母档 9 块的逐色投入展开成多重集，用独立生成器 `torch.Generator().manual_seed(hash(seed, "binfill-nest", tier))` 均匀去掉 9−n 块（n=6／7／8），不消耗环境随机流；于是 `target_i ≤ 母 target_i ≤ 母 spawn_i` 恒成立，派生不会因此失败。代码里 `self.*_cubes_target_number` 等由 target 派生的属性现在在 `_spec.value("objects.target_numbers")` 之前赋值，须挪到其后。xhard4 与只有 xhard4 的三任务不受影响 |
| `utils/unmask_distractor_sampler.py::resample_distractor_layout`／`commit_distractor_layout` | 回注时 `require_replay_match` 用 `final.same_geometry(layout)` 比较「由冻结值拼成的布局」与「本档重抽的布局」；分层回注里外环位置与 `color_order` 取母值，本档重抽结果必然不同（`color_order` 抽在 `randperm(count)` 之后，count 随档变，随机流位置不同），VideoUnmaskSwap／ButtonUnmaskSwap 一回注就抛错 | `recorder.layered` 为真时不做 `same_geometry` 比较，改由 `SpecRecorder` 逐点核「本档抽到值 == `layout_drawn`」（`layout_drift` 计入 `injected_mismatch`）；非分层（v6、xhard4）行为逐字不变 |
| `utils/unmask_swap_xhard.py::_plan_swap_distractors_balanced`／`plan_swap_distractors` | 外环交换现在先在本档重抽的外环布局上规划，之后才注入母布局；规划种子与重排不变时，旧规划被沿用到不同的实际位置上——修掉上一行后这会变成静默错误 | 调整顺序：先把注入后的外环布局提交（`commit_distractor_layout`），再在**实际布局**上规划交换并复核；阶段 3 冒烟覆盖 VideoUnmaskSwap／ButtonUnmaskSwap 四档，并加无仿真反例单测「两档拿到不同候选布局时规划必须随实际布局变」 |
| 同上（Swap 外环 2 个容器的 xhard1） | 外环只剩一个可选对，第 2 个交换窗起只能来回换同一对，靠 fallback 撑住，作废率可能明显高于 v6 的 4 个 | 数值是用户定的（原话 21），不改；阶段 3 冒烟与阶段 4 派生单独统计 VUS／BUS xhard1 的 `derive_fail`，写进留档；余量耗尽即停 |
| `hard_specs.py::TIER_MAX_STEPS` 的余量 | v6 各档 h5 实测最长执行步数 1209／1390／1663／2215（`docs/validation/newtask-v6/hard-split/stage1.md` 的 `TIER_MAX_STEPS_SOURCE=PASS`），上限 1500／1700／2000／2600；v7 把 PickXtimes 抓取次数提到 7／10／12／15，xhard2、xhard3 的余量未知（`site/v6_gt_lengths.json` 的「exec」按视频帧数计，比 h5 执行步数大，不能直接和上限比） | 不预先改上限（它是 README 第 1 节的接口值）。阶段 3 按冒烟局每次抓取的步数外推各档最长执行步数，输出 `V7_STEP_HEADROOM=INFO`；阶段 6 用 gen1 全部 1100 局的 h5 口径（`frames − demo_frames`）逐格核：任一局超过该档上限的 90% 即 `V7_STEP_HEADROOM=FAIL`，停下交用户决定是否调上限 |

## 2. 预算（P3 一次性授权，乘式写法；用户 2026-09-28 全表批准，原话 12、15、23）

| 项 | 乘式 | 上限 |
|---|---|---|
| 母布局 reset（阶段 4，xhard4 配置） | 16 任务 × 30 候选 = 480 次成功目标；抽签上限 14 任务 × 50 + VideoPlaceButton、VideoRepick 2 任务 × 100（原话 23） | ≤ 14 × 50 + 2 × 100 = 900 次 reset |
| 派生 reset（阶段 4） | 13 任务 × 3 档 × 30 候选 = 1170 次，每候选只 1 次、失败不重抽 | ≤ 1170 次 reset |
| **追加候选（阶段 4，原话 24 B2 批准；只对凑不齐 20 局的任务触发，最多一轮）** | 母布局：每任务再 30 候选，抽签上限同原表，最坏 14 任务 × 50 + 2 任务 × 100 = 900；派生：最坏 13 任务 × 3 档 × 30 = 1170 | ≤ 900 + 1170 = 2070 次 reset |
| gen1 轨迹（阶段 6） | (13 任务 × 4 档 + 3 任务 × 1 档) × 20 局 = 1100 局；同步递补上限每格 10 → 55 格 × 10 = 550 | ≤ 1650 次轨迹 |
| gen2 轨迹（阶段 6） | 1100 正式局重放；基础设施失败每身份最多 1 次 | ≤ 1100 + 1100 |
| v6 回归 H 侧（阶段 5，O/P 复用不重跑） | 16 任务 × 3 档 × 3 局 = 144 + (13 任务 × 3 档 + 16 任务 × 1 档) × 3 局 = 165 | ≤ 309（+ 基础设施重跑 ≤ 309） |
| 白名单完整性动态核对（阶段 1，本机单 worker）（原话 23 批准） | 16 任务 × 1 档 × 1 局 xhard4 导出 + 13 任务 × 3 档 × 1 局派生 = 16 + 39 = 55 次 reset，无轨迹 | 55 |
| 本机冒烟（阶段 3，本机单 worker）（原话 23 批准，取代原「1 任务 × (1 + 3) reset + 4 局」） | reset：5 任务 × (1 母 + 3 派生) = 20；轨迹：5 任务 × 4 档 × 1 局 = 20 | 20 reset、20 轨迹 |
| 回注回放（阶段 7） | (13 任务 × 3 档 + 16 任务 × 1 档) × 1 局 = 55 次 reset | 55 |
| 入口冒烟（阶段 7，本机）（原话 23 批准，原表漏记） | BinFill × (xhard0 1 局 + xhard1 1 局) = 2 局 | 2 |
| 评估冒烟（阶段 9） | v7 路线 2 策略 × 2 局（xhard0、xhard1 各 1）= 4；官方路线 2 策略 × 1 局 = 2（单 worker、合计不超过 10，属已授权的官方路线对照任务） | 6 |
| 评估正式（阶段 10） | 2 策略 × (55 格 × 20 局 + 16 任务 × 12 局) = 2 × 1292 = 2584 | 2584 + 基础设施重评每策略每轮 ≤ 65 → ≤ 2844 |
| xhard0 生成 O 侧（阶段 5′）（原话 15 批准） | 16 任务 × 1 档 × 12 局 = 192，官方 `_worker` + `robomme` | ≤ 192（+ 基础设施重跑 ≤ 192） |
| xhard0 生成 H 侧（阶段 5′）（原话 15 批准） | 16 任务 × 1 档 × 12 局 = 192，`robomme_hard` builder 路线 | ≤ 192（+ 基础设施重跑 ≤ 192） |
| xhard0 reset 层对拍（阶段 7）（原话 15 批准） | 2 侧 × 16 任务 × 1 档 × 12 局 = 384 次 reset，本机 GPU 0 | 384 |
| xhard0 官方路线评估对照（阶段 10′）（原话 15 批准） | 2 策略 × 16 任务 × 1 档 × 12 局 = 384 | 384 + 基础设施重评每策略 ≤ 20 → ≤ 424 |
| xhard0 本机冒烟（阶段 3，计入 P3 单 worker 阈值内） | 1 任务 × 1 局 × O／H 两侧 | 2 轨迹 |
| **xhard0 实际放置数探针（已完成 2026-09-28，原话 20 授权）** | 7 任务 × 1 档 × 12 局 = 84 次 reset + smoke 2 次 = 86，本机 GPU 1，无轨迹 | 86（实耗 86，`PROBE_DONE rows=84 errors=0`） |
| **合计：只 reset（不含已完成的探针）** | 母布局 900 + 派生 1170 + 追加候选 2070 + 白名单核对 55 + 冒烟 20 + 回注回放 55 + xhard0 reset 层 384 | **≤ 4654 次 reset** |
| **合计：生成轨迹** | gen1 1650 + gen2 2200 + v6 回归 618 + xhard0 O 侧 384 + xhard0 H 侧 384 + 冒烟 20 + xhard0 冒烟 2 | **≤ 5258 条轨迹** |
| **合计：评估局** | 入口冒烟 2 + 评估冒烟 6 + 评估正式 2844 + 官方路线对照 424 | **≤ 3276 局** |

worker：GL 生成占位 job 每 job 16 worker（1 CPU + 12 G／worker），评估占位 job 每个 4 CPU／32 G；预计耗时以阶段 3 冒烟实测外推后填入本节，不预先编数（阶段 3 通过后、阶段 4 起跑前补齐，仍在已批上限内不需另批）。**标「原话 15 批准」「原话 23 批准」的行与其余行同等效力。**停止条件：任一阶段判定行 FAIL 即停该阶段及其后续，保留产物与日志；任一行实际尝试数将超上限时先停下找用户。

## 3. runbook（命令为拟定形态，参数名以实施时定稿为准）

```bash
# 阶段 0
git show 6e70c0bf:scripts/configs/newtask-v3/subset_manifest.json > scripts/configs/newtask-v3/subset_manifest.json
git archive 6e70c0bf scripts/configs/newtask-v3/official_train | tar -x
for f in src/robomme/env_metadata/test/*.json; do jq -c '{task:.env_id, hard_count:([.records[]|select(.difficulty=="hard")]|length), eps:[.records[]|select(.difficulty=="hard")|.episode]}' "$f"; done
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream
uv run --no-sync python scripts/parity/hard_parity.py export-xhard0-manifest --out scripts/configs/newtask-v7/xhard0_manifest.json   # → XHARD0_IDENTITY

# 阶段 0′（本机）：拉回 O／P 缓存并逐局核 sha，核锚点等价，再打 tag
hf buckets cp -R hf://buckets/HongzeFu/robomme-hard-parity/O-1fadc0e-a40/native artifacts/newtask-v7/parity/h5/O-native
hf buckets cp -R hf://buckets/HongzeFu/robomme-hard-parity/H-34a1cea-a40/native artifacts/newtask-v7/parity/h5/P-native
hf buckets cp -R hf://buckets/HongzeFu/robomme-hard-parity/H-b1afc80-a40/xhard artifacts/newtask-v7/parity/h5/P-xhard
(cd artifacts/newtask-v7/parity/h5/O-native && sha256sum -c SHA256SUMS*)   # P-native、P-xhard 同法；任一 FAILED 即停
git diff --stat 34a1ceab ce3843b4 -- src/robomme_hard scripts/parity scripts/injection-dev pyproject.toml uv.lock   # 逐文件判据见 §7.7
git diff --stat b1afc804 ce3843b4 -- src/robomme_hard scripts/parity scripts/injection-dev pyproject.toml uv.lock
uv run --no-sync python scripts/parity/hard_parity.py anchor register --tag parity-anchor-v6 --commit ce3843b4 --h5-root artifacts/newtask-v7/parity/h5 --segments native:P-native,xhard:P-xhard   # → PARITY_ANCHOR

# 阶段 1（本机，GPU 0，单 worker）：白名单完整性动态核对
uv run --no-sync python scripts/injection-dev/derive_specs.py --whitelist-check --tasks all --workers 1 --gpus 0 --out artifacts/newtask-v7/whitelist-check   # → LAYOUT_WHITELIST_COMPLETE

# 阶段 3（本机，GPU 0，单 worker）
uv run --no-sync python scripts/parity/hard_parity.py generate --side O --tier xhard0 --manifest scripts/configs/newtask-v7/xhard0_manifest.json --src-root <1fadc0ec worktree> --workers 1 --gpu 0 --smoke 1 --dev-smoke --out artifacts/newtask-v7/smoke/O-xhard0
uv run --no-sync python scripts/parity/hard_parity.py generate --side H --tier xhard0 --manifest scripts/configs/newtask-v7/xhard0_manifest.json --src-root . --workers 1 --gpu 0 --smoke 1 --dev-smoke --out artifacts/newtask-v7/smoke/H-xhard0
uv run --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard4 --tasks BinFill,VideoUnmask,ButtonUnmask,VideoUnmaskSwap,ButtonUnmaskSwap --seed-profile v7 --candidates-per-env 1 --select 0 --workers 1 --gpus 0 --out artifacts/newtask-v7/smoke/xhard4/specs.jsonl
uv run --no-sync python scripts/injection-dev/derive_specs.py --parent artifacts/newtask-v7/smoke/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --whitelist src/robomme_hard/env_metadata/test-hard/layout_whitelist.json --out-root artifacts/newtask-v7/smoke --workers 1 --gpus 0
uv run --no-sync python scripts/parity/hard_regression.py layout-shared --specs-root artifacts/newtask-v7/smoke
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs artifacts/newtask-v7/smoke --output artifacts/newtask-v7/smoke/rollout --workers 1 --gpu 0 --dev-smoke
ROBOMME_HARD_SPECS_ROOT=artifacts/newtask-v7/smoke uv run --no-sync python scripts/parity/hard_regression.py reset-replay --specs-root artifacts/newtask-v7/smoke --out artifacts/newtask-v7/smoke/reset-replay

# 阶段 4～6（GL 占位 job 内 srun --overlap --gpu_cmode=shared；先 --dry-run 打印预算再起 tmux）
uv run --frozen --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard4 --tasks all --seed-profile v7 --candidates-per-env 30 --select 0..19 --max-reset-attempts 50 --task-max-reset-attempts VideoPlaceButton=100,VideoRepick=100 --workers 16 --gpus 0 --out <NFS>/v7/xhard4/specs.jsonl
uv run --frozen --no-sync python scripts/injection-dev/derive_specs.py --parent <NFS>/v7/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --whitelist src/robomme_hard/env_metadata/test-hard/layout_whitelist.json --out-root <NFS>/v7 --workers 16 --gpus 0
uv run --frozen --no-sync python scripts/parity/hard_regression.py prefix-geometry --specs-root <NFS>/v7   # → V7_PREFIX_GEOMETRY
# 阶段 5（v6 回归，只生成 H；O／P 用阶段 0′ 拉回的缓存）
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json --src-root <GL_REPO> --workers 16 --gpu 0 --out /tmp/hs/H-native --stage <NFS>/hs-stage/H-native
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H --tier xhard --manifest <parity-anchor-v6 登记表中 P-xhard 段的 165 局身份清单> --src-root <GL_REPO> --workers 16 --gpu 0 --out /tmp/hs/H-xhard --stage <NFS>/hs-stage/H-xhard
# 阶段 5′（O、H 各在一个占位 job 内，O 侧 src-root 为 1fadc0ec worktree、进程只导入 robomme）
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side O --tier xhard0 --manifest scripts/configs/newtask-v7/xhard0_manifest.json --src-root <1fadc0ec worktree> --workers 16 --gpu 0 --out /tmp/hs/O-xhard0 --stage <NFS>/hs-stage/O-xhard0
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H --tier xhard0 --manifest scripts/configs/newtask-v7/xhard0_manifest.json --src-root <GL_REPO> --workers 16 --gpu 0 --out /tmp/hs/H-xhard0 --stage <NFS>/hs-stage/H-xhard0
# 阶段 6（gen1 带同步递补；gen2 在另一个占位 job 上按 gen1 交付清单重放）
uv run --frozen --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs <NFS>/v7 --output <NFS>/v7/gen1 --workers 16 --gpu 0   # 收尾写 <NFS>/v7/gen1/delivery.json → V7_DELIVERY_SET
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H2 --tier v7 --manifest <NFS>/v7/gen1/delivery.json --specs-root <NFS>/v7 --src-root <GL_REPO> --workers 16 --gpu 0 --out /tmp/hs/H2-v7 --stage <NFS>/hs-stage/H2-v7
# 每个分段的暂存目录在该段 GENERATE 判定行出现后 touch SEGMENT_DONE，hard_pull 才会收尾（同 v6 stage4 做法）

# 本机比对（目录一律显式传，不依赖 v6 默认值）
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/hs-stage --dest artifacts/newtask-v7/parity/h5 --segments H-native,H-xhard,O-xhard0,H-xhard0,H2-v7
uv run --no-sync python scripts/parity/hard_parity.py import-delivery --side H --tier v7 --delivery artifacts/newtask-v7/gen1/delivery.json --h5-root artifacts/newtask-v7/parity/h5   # gen1 → H-v7 的 identities.jsonl
for pair in O:P P:H O:H; do uv run --no-sync python scripts/parity/hard_parity.py compare --pair $pair --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json --p-anchor parity-anchor-v6 --h5-root artifacts/newtask-v7/parity/h5 --compare-root artifacts/newtask-v7/parity/compare; done
uv run --no-sync python scripts/parity/hard_parity.py compare --pair P:H --tier xhard --manifest <同上 165 局身份清单> --p-anchor parity-anchor-v6 --h5-root artifacts/newtask-v7/parity/h5 --compare-root artifacts/newtask-v7/parity/compare
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:H --tier xhard0 --manifest scripts/configs/newtask-v7/xhard0_manifest.json --h5-root artifacts/newtask-v7/parity/h5 --compare-root artifacts/newtask-v7/parity/compare
uv run --no-sync python scripts/parity/hard_parity.py compare --pair H:H2 --tier v7 --manifest artifacts/newtask-v7/gen1/delivery.json --h5-root artifacts/newtask-v7/parity/h5 --compare-root artifacts/newtask-v7/parity/compare
uv run --no-sync python scripts/parity/hard_parity.py publish --side O --tier xhard0 --prefix O-1fadc0e-a40 --h5-root artifacts/newtask-v7/parity/h5   # → BUCKET_SYNC
rsync -a <NFS>/v7/xhard{1,2,3,4} <NFS>/v7/v7-candidate-pool.json artifacts/newtask-v7/specs/   # v7 规格拉回本机（阶段 8 换包前，阶段 7 用覆盖根读它）
ROBOMME_HARD_SPECS_ROOT=artifacts/newtask-v7/specs uv run --no-sync python scripts/parity/hard_regression.py reset-replay --specs-root artifacts/newtask-v7/specs --out artifacts/newtask-v7/reset-replay
uv run --no-sync python scripts/parity/hard_regression.py xhard0-reset-parity --src-root <1fadc0ec worktree> --gpu 0 --out artifacts/newtask-v7/xhard0-reset-parity   # → XHARD0_RESET_PARITY / XHARD0_DEMO_DIFF
ROBOMME_HARD_SPECS_ROOT=artifacts/newtask-v7/specs uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 0
ROBOMME_HARD_SPECS_ROOT=artifacts/newtask-v7/specs uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 12
uv run --no-sync python scripts/parity/hard_regression.py xhard0-eval-parity --official <官方路线终态记录> --hard <v7 评估 episodes.jsonl> --policy simplememvla   # → XHARD0_EVAL_PARITY=INFO
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

长任务一律 detached tmux（会话名前缀 `v7-`，清单记入留档）+ Monitor 行缓冲过滤管道，过滤词含 `NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|Traceback|EXIT_CODE=|全部完成`。集群操作按 `greatlakes.md`（48 h 占位 job、`--gpu_cmode=shared`、跑完按清单逐个 `scancel`）。

### 3.1 评估与视频搬运（阶段 9～10）

- 策略侧改动清单（新增在上次分支之上）：SimpleMemVLA 在 `testhard_eval.py` 里打开逐局 mp4 写出（若官方 `eval_success` 已有视频开关就只传参数；没有就在 `testhard_eval.py` 里用 `imageio` 写前视帧，不改官方文件）；MME-VLA 官方本来就逐局存视频，只把输出目录指到 NFS 暂存目录，并取消上次「每格只留 1 条」的删除步骤。
- 搬运脚本放在 `scripts/injection-dev/eval_video_mover.py`（P1：不进 `scripts/` 顶层）：`--stage <NFS 暂存> --dest artifacts/newtask-v7/eval-videos/<策略> --policy {simplememvla,mmevla} --identities artifacts/newtask-v7/eval-identities-1292.jsonl --stable-sec 10`；按 `--policy` 选终态记录（SimpleMemVLA `results-shard*.jsonl`、MME-VLA `episodes.jsonl`）与视频命名规则，按 `(task, episode)` 关联、从清单反查 seed 写进目标文件名，重评多行取最后一个终态行；循环扫描 → rsync → 核对 sha256 → 删 NFS 副本 → 往 `moved.jsonl` 追加一行；每 60 秒打印 `VMOVE moved=<n> pending=<n> bytes=<n>`，结束时打印 `EXIT_CODE=`。在 tmux `v7-vmove-<策略>` 里运行，用 Monitor 盯 `VMOVE|Traceback|EXIT_CODE=`。
- 视频不进 git，也不进 bucket；留档只记清单与 sha256 的汇总。

## 4. 风险登记

| 风险 | 处置 |
|---|---|
| 白名单漏路径或拼错 | R10 闭世界：未分类路径直接 `EpisodeSpecError`；阶段 1 动态核对 55 次 reset 覆盖 xhard4 与三个低档，`LAYOUT_WHITELIST_COMPLETE` 要求 `unclassified=0` 且每个模式至少命中一次；`V7_LAYOUT_SHARED` 另做反向核对（非 G 路径的值都等于母值、必需 L 路径不许缺席） |
| BinFill 低档投入超过母布局摆放数 | D-15 嵌套派生消除（§1.8）；`test_v7_binfill_nested.py` 钉 `target_i ≤ 母 target_i` |
| UnmaskSwap 分层回注的 `same_geometry` 冲突、交换规划落在错误布局上 | §1.8：分层模式改核 `layout_drawn`，注入后在实际布局上重新规划；阶段 3 冒烟四个 Unmask 类任务四档全跑 |
| Swap 两任务 xhard1 外环只有 2 个容器、交换靠 fallback | 单独统计 `derive_fail`；余量耗尽即停 |
| 第 4 干扰色与目标色难以区分 | 阶段 3 出图目视（Read 看图），橙色不过关就换备选色；不影响 Unmask 的三色池（R11） |
| v7 抓取次数上调后超过 `TIER_MAX_STEPS` | `V7_STEP_HEADROOM`（§1.8）：超上限 90% 时按 §1 第 9 条 B4 把该档上限上调为实测最大步数 × 1.25 向上取整到百，不回调抓取次数，改动记留档与 README（用户 2026-09-29 预定） |
| 容差只标定了原三档，用在 v6 xhard 与 v7 上属于外推 | 超容差时不放宽、不重标；按 §1 第 9 条 B3 预定规则自动分类：`first_divergence` 在首次 RRT 规划之后且两侧重规划次数不同 → `noise` 只报告；在 reset 或首次规划之前 → FAIL 停；任一 pair 超容差局数 > 5% 不论分类一律停下找用户（用户 2026-09-29 预定）。`compare` 报告逐局列 `first_divergence`、两侧 RRT 重规划次数与分类 |
| test 的 hard seed 从未生成过，个别局可能两侧同样规划失败 | `compare` 单列 `both_fail`，不当作不一致；`both_fail>0` 附原因表交用户 |
| 派生时外环交换／额外放台不可行（VUS/BUS/VPB） | 计入 `derive_fail`，四档同步作废该候选；候选留 10 个余量（用户定 30 候选）；余量耗尽按 §1 第 9 条 B2 对该任务追加一轮 30 候选（预算已批），仍不足则接受少于 20 局并留档，不做第二次追加、不放宽定值 |
| 前缀在低档下不合法（理论上不会） | 环境里的复核不覆盖所有任务，不依赖它；阶段 4 派生后跑离线 `V7_PREFIX_GEOMETRY` 逐行重算区域与最小中心距；出现即视为白名单分类错误，回到阶段 1 |
| 派生规格的 `layout_drawn` 与回放不等（随机流漂移） | `layout_drift>0` 计入 `injected_mismatch`，`V7_RESET_REPLAY` FAIL；不放宽 |
| `record()` 点在派生局与母局不同（如 `objects.distractor_count`） | 派生规格只含本局实际值，回放比对的是派生规格，不比母局 |
| 同步递补让四档目录锁竞争 | 目录锁 + 单写者；`--self-check` 核 identity 未变 |
| gen1/gen2 落在不同型号卡 | gen1 的 `generate_h5.py` 与 gen2 的 `hard_parity.py generate` 都做 A40 断言；launch 记 GPU 名与驱动，`compare` 前核对相同，否则只报容差、不报 `sha_equal` |
| 144 清单来自官方 train 元数据，不含 test 的 hard seed | 阶段 5′ 用 `xhard0_manifest.json`（test 元数据 hard 子集）对 192 个身份逐一做 O:H 对拍，不再依赖 144 清单间接推断 |
| xhard0 走官方 `_worker` 时 `EpisodeJob.recovery_mode` 按 episode 号定（≤2 z、≤5 xy） | 两侧 job 都用原 test episode 号，只有 episode 3 带 `xy` 恢复，O、H 相同（R9）；`identities.jsonl` 记 `recovery_mode`，compare 前核两侧相等；评估路线不开恢复是官方本来的口径，不算不一致 |
| H 侧 builder 路线取到的环境参数与官方 `_worker` 不同（多键或值不同） | worker 断言键集合恰为 `{seed, difficulty}` 且值等于 job，不同即抛错、该局记 infra 失败，不静默回退到直接拼参数 |
| 官方路线策略评估的 `episodes.jsonl` 没有 seed 字段 | 官方侧脚本按 `(task, 原 episode 号)` 记录，`xhard0-eval-parity` 用 `xhard0_manifest.json` 把原 episode 号映射到 seed 再对齐；映射缺失即 FAIL |
| reset 层对拍在本机 Ada 上做、正式生成在 A40 | reset 层两侧在同一张卡同一进程序列里比，比的是同卡下两条代码路线是否逐位相同，不跨卡；跨卡差异由阶段 5′ 的 A40 容差对拍覆盖。演示回放受 RRT 墙钟噪声影响，只作报告层（D-16） |
| NFS 暂存被视频塞满或搬运进程挂掉 | 搬运与评估解耦；Monitor 盯 `VMOVE`，停更超过 10 分钟就重启搬运；暂存目录超过 200G 时通知用户 |
| 本机 `/data` 不够放 gen1／gen2／xhard0／缓存／视频 | 按 §1 第 9 条 B5 顺序只删重复缓存与已上 bucket 的内容（O／P 缓存 → gen2 → xhard0 O 侧），视频与 gen1 不删，尽可能不停；三项删完仍不够才停（用户 2026-09-29 预定；`/data` 当前剩 5.2T） |
| 两个策略仓库读 `spec_binding` 字段 | 新增键只增不改；xhard0 返回导出模式（`available=True, mode="export"`），策略仓库与合并脚本里「全部局都是 replay」的断言改为按档分类计数（§5 第 4 条）；阶段 9 冒烟覆盖 xhard0 与 xhard1 各 1 局 |

## 5. 盲区诚实清单

- 白名单与「前缀合法」结论来自静态审计，未运行任何环境；阶段 1 的动态核对与阶段 3 的冒烟是第一批动态证据。
- 派生失败率未知；30 候选是否够 20 局要看阶段 4 实测，不够即停。BinFill 的「三档联合约 28%」是改用嵌套派生之前的估算，嵌套后这一失败源消失，但其他失败源（如 Swap 外环 2 容器的交换）仍未实测。
- 母布局单次抽签成功率沿用 v6 的 draw_stats（VideoPlaceButton 约 34%、VideoRepick 约 39%）；v7 数值变了，实际成功率可能不同，100 次上限是否够看阶段 4。
- 两次生成的 `sha_equal` 期望值不承诺（V6 时 P:H xhard 165 对逐字节相同，但 RRT 噪声存在）；判定只看容差与判定层。
- 跨型号容差从未标定；本机 Ada 与 aspen A6000 的任何 v7 产物都不进正式对拍。
- 本文未估算耗时；以阶段 3 单格实测外推后补。
- xhard0 生成对拍是首次对 test 的 hard seed 做 O:H；此前 144 局（train 元数据）O↔H 逐字节相同只能说明路线一致，不能替代 192 局的实测结论。
- 策略层对照只报告（D-16）：策略推理本身不确定，终态差异不能归因于路线；环境路线一致性由 reset 层确定性部分与生成层 O:H 判定。
- 梯度定值后的未验证项：Unmask xhard1 干扰 `count=0` 放宽后的整局从未跑过；第 4 干扰色的可分辨性未出图核对；八处顶档下调与抓取次数上调后的执行步数余量未实测（`V7_STEP_HEADROOM`）。均以阶段 3 冒烟与阶段 4、6 实测为准。
- 两个策略仓库在本仓库之外，§5 列出的接线（清单分片、绑定分类、`srun` 4 CPU、视频、官方路线开关）的具体改动点未在本仓库核对，阶段 9 各自冒烟为准。
- xhard0 放置数探针只测了 7 个会浮动的任务的 12 个 test hard seed；train／val 的 hard 局与其他任务未测，PatternLock「1000 次不合格用最后一条」的触发率未测。

## 6. 留档与 commit 纪律

- 方案修订只提交本文件：`git diff --check`、`grep -c '^# 第一部分\|^# 第二部分'` 等于 2、链接目标存在；逐路径 `git add`，中文 commit（编号从 `git log` 最近一次接续）后立即 push。
- 实施各阶段：阶段 1～2 各一个 commit；阶段 4～6 起跑前 HEAD 精确等于所跑代码（起跑到 gen2 完成之间不 commit）；留档 `docs/validation/newtask-v7/`（判定行内联原文、GPU／驱动／依赖指纹、真实尝试计数、首个差异、退出码、输出路径、tmux 会话与 JobID 清单）；gen1 正式局 h5 搬回本机 `/data` 保留；gen2 在 `PARITY_V7_TWICE=PASS` 并留档后删除（用户定「gen2 比完即删」），删除前先冻结逐身份 sha、比对明细（`compare/summary.json` 与逐局指标）、gen2 的生成提交与规格摘要，并写出精确删除清单（逐文件路径，不用 glob），删后核对清单外无文件受影响；NFS 与 `/tmp` 不留大文件。
- 不把本文写入规则文件、不追加历史账本；用户原话与判定行按第 22 条进 commit body 与留档。

## 7. 机制、接口、验收与 parity 细节

第二部分内的「§N」指第二部分同号小节，「§7.x」指本节各小节；「第一部分 §N」指第一部分同号小节。

### 7.1 口径编号表（D-1～D-18，第二部分引用用）

| 编号 | 口径 | 依据 |
|---|---|---|
| D-1 | xhard0 = 官方 test 的 `difficulty=="hard"` 记录，seed 逐条照抄元数据（不套公式），运行难度传 `"hard"`，不进新值族、不回注；**生成与评估都走 `robomme_hard`**，生成结果与官方 `dataset-gen` 生成器（O 侧）容差内一致；评估一致按 D-16 判定 | 12.222 §2、§3；原话 13、14；本文 §2 |
| D-2 | xhard0 每任务 12 局（官方 test 每任务 50 = easy 26 / medium 12 / hard 12，原 episode 号 3,7,…,47） | 12.222 用户决定「和test的hard数量一致」；本文引言 |
| D-3 | xhard1～4 每任务 20 个母布局，四档同一布局、同一 seed；13 个有梯度任务四档共用，StopCube／InsertPeg／MoveCube 只有 xhard4、母布局即自身 | 原话 2；第一部分 §3 |
| D-4 | 「布局」= 各环境取值点里与梯度无关的位置／颜色／朝向／槽位／初始化类点（白名单见第二部分 §1.3）；「梯度」= 次数、数量、序列、演示选择类点，按档现场重抽 | 原话 2「只有现在的梯度区别不一样」；第一部分 §3.2 |
| D-5 | 梯度维度沿用现行四档表；**数值改为 §3.2.2 定值表**：每档单点、无区间；数量类按目视总量等差、以 xhard0 实测放置数（§3.2.1）为基线、xhard1 只比 xhard0 难一点点；等差冲突时下调顶档不上调低档。原话 2 附表只作历史对照 | 原话 17～21；第一部分 §3.2 |
| D-6 | 接口与 `scripts/README.md` 第 1 节四处差别完全一致：`dataset="test-hard"`、`resolve_episode → (seed, tier)`、`TIER_MAX_STEPS[tier]`、`make_env_for_episode(ep, max_steps=…)`；只多一个档名 `xhard0` 与一个步数项 `1300` | 原话 4；§7.4 |
| D-7 | 发布名 v7：包内规格换成 `hard-specs/3`（含 v7 seed 规则与母布局字段），产物落 `artifacts/newtask-v7/`，留档落 `docs/validation/newtask-v7/`；V6 规格文件由 git 历史保留 | 原话 5；§7.5 |
| D-8 | 对拍分三类：v6 回归 OPH（D-11/D-12，取代原「只做 `PARITY_O_H`」，原三档 144 + v6 xhard 165）、`PARITY_V7_TWICE`（v7 全部 1100 正式局两次生成，同型号 A40、不同作业）、xhard0 O:H（192，原话 13～15 在原话 6 之外新增，首次无 P 侧）；容差沿用现行 `hard-parity-tolerances.json`，不重标 | 原话 6、13～15；第一部分 §4.2 |
| D-9 | 集群侧生成一律 A40@greatlakes 占位 job；两次生成必须同型号同驱动，否则只能做容差内一致、不能报 sha 相等数 | 第一部分 §4.3、§7.8 |
| D-10 | 母布局候选数、递补规则等取整类细节由 agent 自定并写进本文，不再逐项询问（用户 2026-09-24「以后四舍五入这种问题都不要来找我」）；xhard0 是否生成 h5 已由原话 13 定死（要生成），不再属本条 | 记忆规则 |
| D-11 | **parity 锚点机制（以后都这么做）**：O = 官方 `1fadc0ec` 的存档产物，只生成一次、永久复用；P = 打 tag 的**固定锚点 commit** 的产物（不再是「修改前」）；H = 当前 HEAD。每次对拍都比 O:P、P:H、O:H。产物按 commit sha 缓存，**已验证过的 commit 不再重新生成**，P 侧直接复用它当年作为 H 的产物 | 原话 7、8；第一部分 §4、§7.7 |
| D-12 | v7 顺序：`ce3843b4` 打 tag `parity-anchor-v6`（v6 OPH 已在其等价代码上完成）→ 实施 v7 → 以 `parity-anchor-v6` 为 P 再跑一次 v6 OPH（原三档 144 + v6 xhard 165）并存档 → v7 验收全过后打 tag `parity-anchor-v7`，此后 P 一律取 `parity-anchor-v7` | 原话 8、9；第一部分 §4.2、§7.7 |
| D-13 | 容差只在 A40 上成立：O/P/H 三侧与缓存复用都要求 A40 + 同驱动（595.71.05）；驱动或型号不同的缓存不得作 P，只能重新生成 | 原话 8；§7.8 |
| D-14 | 「以前」= 官方 `dataset-gen` 分支：生成 `d53f21a7:scripts/data-generation/generate_dataset.py`（vendor 原文）+ `1fadc0ec` 源码，评估 `scripts/evaluation.py` + `robomme` builder `dataset="test"`；xhard0 的 O 侧与官方路线评估对照只能用这两样，不得用 `robomme_hard` 或任何改写 | 原话 14；R9 |
| D-15 | BinFill 低档逐色投入按母档嵌套派生：母档 9 块的逐色投入里去掉 3／2／1 块得到 xhard1／2／3 的 6／7／8 块，保证不超过母布局摆放数；`objects.target_numbers` 归 N 表 | 原话 23「A 嵌套派生」；§1.8 |
| D-16 | xhard0「评估一致」的判定层是 reset 层确定性部分（演示回放前的仿真状态、seed、任务目标、多选项、`gym.make` 实参与包装链逐位相同）；演示层与策略层只报告 | 原话 23「A 环境层判、策略层只报告」；第一部分 §2 |
| D-17 | 母布局抽签上限：VideoPlaceButton、VideoRepick 每任务 100 次，其余 50 次 | 原话 23「A 两任务提到 100 次」；§2 |
| D-18 | 修补追加预算（阶段 1 的 55 次 reset、阶段 3 净增 16 次 reset 与 16 条轨迹、阶段 7 的 2 局冒烟）已批准，并入 §2 预算全表 | 原话 23「全部批准」；§2 |
| D-19 | Swap 两任务外环容器归 N 表：低档用母布局外环按角度排序后的一段连续弧（k 个相邻容器），依次试 n 个起点、取第一段在本档内环扫掠护栏与整段外环交换规划（含按钮避让）下可行的弧；选中结果冻结进派生规格（`layout_nest_context` 留痕），回注不重算。位置、朝向逐字取自母布局，「布局共用」的本意不变，只是把「按放置序取前 k 个」换成「取可行的相邻 k 个」 | 阶段 1／3 实测 BUS xhard1 全部 `btn` 拒绝；原话 30 授权 agent 自行处理 |
| D-20 | xhard0 reset 层对拍的演示前状态：每局另起一次底层环境（同一 `gym.make` 实参、无包装链）`reset()` 后取 `get_state_dict()` 摘要；评估链 reset 另取 task_goal、多选项与演示层 | 原话 28「批准增至 768 次」 |

### 7.2 数量：v7 每任务多少局、编号怎么排

| 档 | 来源 | 任务数 × 局数 | 合计 |
|---|---|---|---|
| xhard0 | 官方 test hard 子集，原生 hard | 16 任务 × 1 档 × 12 局 | 192 |
| xhard1～3 | 母布局派生 | 13 任务 × 3 档 × 20 局 | 780 |
| xhard4 | 母布局本体 | 16 任务 × 1 档 × 20 局 | 320 |
| 合计 | — | 16×1×12 + 13×3×20 + 16×1×20 | **1292** |

builder 的 episode 号按「xhard0 → xhard1 → xhard2 → xhard3 → xhard4，档内按候选号升序」排：13 个有梯度任务 0～11 是 xhard0、12～31 xhard1、32～51 xhard2、52～71 xhard3、72～91 xhard4，共 92 局；三个只有 xhard4 的任务 0～11 xhard0、12～31 xhard4，共 32 局。**这与 12.222 的「xhard0 追加在末尾以保住旧编号」不同**：v7 的 xhard1～4 全部重抽，旧编号本来就保不住，所以直接按档序排、以后不再挪。

为什么 xhard0 不能同时是「与 hard 完全一致」又是「20 个母布局之一」：母布局是在 xhard4 配置下抽出来的场景（例如 VideoUnmask 12 个干扰容器、PatternLock 24 节点），而原生 hard 的场景由官方代码在 hard 配置下抽（0 个干扰容器、4～8 节点）；MoveCube 的 hard 是原生场景、xhard4 是圆环 U，VideoRepick 的 hard 甚至是另一种任务机制。要让 xhard0「和原本的 hard 完全一致」，它就只能走官方 hard 路径、用官方 test 的 seed，与母布局无关。**这是 D-1／D-3 并列而不合并的原因。**

xhard0 身份的静态核实（12.222 已用 `jq` 做过，本轮重跑一次原样）：16 个任务全部 hard 12 局、原 episode 号 `3,7,11,15,19,23,27,31,35,39,43,47`；seed 逐条来自元数据（例如 PickXtimes 原 episode 15 的 seed 是 `511501` 而非公式值 `511500`，BinFill 原 episode 3 的 seed 是 `540302`）。

### 7.3 机制：母布局怎么来、低档怎么共用

#### 7.3.1 现状为什么做不到共用

- 现在四档各有一套 seed 偏移（[`hard_specs.py`](src/robomme_hard/env_record_wrapper/hard_specs.py)::`V6_SEED_OFFSETS`：xhard4 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6），布局天然互不相同。
- 回注通道 [`episode_spec.py`](src/robomme_hard/robomme_env/utils/episode_spec.py)::`SpecRecorder.value` 在回注模式下**对每个取值点都先按本局 seed 真抽一次，再拿抽到的值与冻结值比对，最后返回冻结值**；`hard_specs.py::spec_binding` 把所有 value 点的不等都计入 `injected_mismatch`，而 [`hard_regression.py`](scripts/parity/hard_regression.py) 的 `reset-replay`／`eval-smoke` 要求它为 0。因此「把 xhard4 的规格改一改喂给 xhard1」会在每个布局点都记一条不等，直接触发闸门。
- 仓库里没有「给定母规格派生各档规格」的入口：[`generate_h5.py`](scripts/injection-dev/generate_h5.py) 的 `--mode replay` 只按 `(task, tier, seed)` 去已有规格行里查；`freeze_specs.py` 只会 reset 抽签。
- 纯 JSON 截断（xhard4 规格按低档数量取前缀）对 PickXtimes／SwingXtimes／PickHighlight／PatternLock／RouteStick 可行，但对 VideoRepick（`swap_initiators_remaining` 必须是 range(k−1) 的完整排列、`swap_pairs` 引用 ≥k 的块、可行图 G 随块集合变化）、VideoPlaceButton xhard1/2（台数 5→4、额外放台候选按占用表重算）、VideoUnmaskSwap／ButtonUnmaskSwap（`cube_bins`／`label_perm` 与 count 耦合、外环规划要重跑可行性）不可行，BinFill 的 `target_numbers` 是每色聚合值也没有「前缀」可取。**所以不能靠改 JSON，必须让梯度类取值点在环境里现场重抽。**

#### 7.3.2 分层回注：布局注入、梯度重抽、记录点重导出

定义：每个环境的取值点分三类（白名单在第二部分 §1.3，闭世界见 R10）；除下面的 L、G 外，另有**嵌套类** `N`：只有 BinFill 的 `objects.target_numbers`，值由母值嵌套派生（D-15）。**布局类** `L`：位置、颜色、朝向、槽位、初始化、type_choice 之类，与档位无关或只随数量变长；**梯度类** `G`：`num_repeats`、`n_swaps`、`n_picks`、`target_numbers`、`cube_count`、`cube_bins`、`label_perm`、`swap_plan_seed`、`swap_pairs.k`、`highlight_*`、`demo_ids`、`visit_*`、`L` 等。记录点（`record()`）全部视为派生量，由派生运行重新导出。

```text
阶段 A  母布局抽签（每任务 30 个候选，xhard4 配置，v7 seed 规则，只 reset）
        ├─ 13 个有梯度任务：母布局规格 = xhard4 规格本体（spec_kind native-newvalue/2，mismatch=0）
        └─ StopCube / InsertPeg / MoveCube：同上，只此一档
阶段 B  派生（13 任务 × 3 档 × 每候选 1 次 reset，「layered」模式）
        native_episode_spec = {"envelope":"derive", "parent":母规格, "layout":白名单[task]}  → SpecRecorder 进入 derive 模式
        ├─ 路径 ∈ L：照常抽一次（随机流不漂移），返回母值；列表值按 len(抽到值) 取前缀；
        │            逐项路径（layout.distractors.<color>_0、layout.cubes.i、layout.targets.i、
        │            objects.distractors.bins.i、actions.directions.i）低档只访问前 k 个，多出的自动 unused
        ├─ 路径 ∈ N：照常抽一次（记 layout_drawn），返回母值的嵌套派生值（§1.8）
        ├─ 路径 ∈ G：照常抽、照常用（本档 config 决定取值）
        ├─ 路径都不属于 L／G／N：抛 EpisodeSpecError（R10）
        ├─ record()：照常记本档实际值
        └─ 导出：spec_kind="native-layered/3"，spec 树 = 本局实际使用值；
                  另存 layout_parent{spec_sha256, tier="xhard4", candidate}、layout_drawn{path: 本档抽到的值}
阶段 C  生成 h5（55 格 × 20 局，回注模式）
        └─ 回注 native-layered/3：L／N 点比对对象改为 layout_drawn（逐位，核随机流），使用值 = 冻结值；
           G 点与原来一样比冻结值；spec_binding 新增 layout_hit／layout_overridden／layout_drift，injected_mismatch 仍须 0
```

⚠ 陷阱与反例：
- **不能用「四档同 seed、让 RNG 自己碰」代替注入**。同 seed 下 PickXtimes／SwingXtimes／VideoUnmask／PickHighlight／RouteStick 节点的布局前缀按代码顺序推断会逐位相同，但 BinFill（`target_numbers` 逐单位抽样次数随 put_in 变，后面 spawn 分配、槽位整体平移）、VideoPlaceOrder（`count_order` 只在 xhard1/3 抽，属只在低档出现的取值点，阶段 1 的派生核对会覆盖到）、PatternLock（搜索循环停在不同尝试次数）都不会相同；而且「天然相同」是推断不是保证。v7 用注入保证，同 seed 只是顺带（D-3 四档同 seed 便于身份对齐）。
- **前缀合法性靠什么保证**：依序放置的对象只对已放对象做中心距／OBB 检查，前缀天然合法；四档的区域、最小中心距、内环 bin 数（VU/BU 8 个、VUS/BUS 4 个）、BinFill 12 槽相同，母布局在 xhard4 下合法 ⇒ 前缀在低档下合法。环境里的复核（`object_generation.py::_assert_center_rules_hold`、`BinFill._spawn_cubes_xhard` 槽位复核、`PatternLock._check_xhard_path` 等）只覆盖部分任务：PickHighlight 没有复核，随机 bin 的障碍检查发生在 `recorder.value` 替换之前，derive 模式下 `verify_distractor_layout` 也不跑，`swap_uniform.verify_swap_sequence` 查的是交换序列而不是位置。所以另加离线闸门 `V7_PREFIX_GEOMETRY`（§7.6），不把环境复核当保证。
- **派生仍可能失败**：梯度点现场重抽可能撞上 `SceneGenerationError`（外环交换某窗不可行、额外放台无候选），这时该候选在**四档同步作废**，按候选号顺延，不允许某档单独换布局（否则「同一布局」不成立）。
- **PatternLock 没有布局**：它唯一的取值点是 `actions.path_nodes`，v7 把它当作可取前缀的布局点（xhard4 的 24 节点路径，低档取前 12／16／20 个节点，8 邻接不重访的前缀仍合法）；RouteStick 的 `actions.nodes` 同理。这是 D-10 范围内的自定细节。
- **只把 `objects.num_repeats` 之类标量留给现场取值**，不把 xhard4 的 15 次硬塞给 xhard1：代码里没有按档区间的 `_assert_*`，梯度值与本档定值不等时由 `SpecRecorder.value` 记为 mismatch、计入 `injected_mismatch`，回注闸门随之 FAIL；定值后「现场取值」就是取该档唯一的数。

收益（静态盘点，未实测）：PickXtimes／SwingXtimes／PickHighlight／VideoUnmask／ButtonUnmask／RouteStick／PatternLock 只需白名单（VideoUnmask／ButtonUnmask 另需放宽 `count=0`）；VideoPlaceOrder／VideoPlaceButton／VideoRepick 由「梯度点现场重抽」消掉耦合；BinFill 需要嵌套派生（D-15），VideoUnmaskSwap／ButtonUnmaskSwap 需要 §1.8 的采样器与规划改动，**只靠现场重抽不够**；三个 xhard4 独有任务不涉及派生。

#### 7.3.3 seed 与身份

v7 seed 规则（`hard_specs.py` 新增 profile `"v7"`）：`seed = 14_000_000 + env_code × 100_000 + candidate × 100 + attempt`，**四档同一 offset**，同一候选号在四档里 seed 相同；与 V5 段（4e6）、V6 四段（6e6～12e6）互不重叠。`validate_specs` 对 v7 文件要求：四档 header 的 `seed_rule` 相同；每行 `seed` 等于公式；派生行的 `layout_parent.spec_sha256` 等于 xhard4 同候选行的 `spec_sha256`。

身份键仍是 `(task, tier, seed)`（[`hard_parity.py`](scripts/parity/hard_parity.py)::`ident`），同 seed 跨档靠 tier 区分。`resolve_identity` 对派生行多返回 `layout_parent`，对 xhard0 返回 `source_dataset="test"`、`source_episode`、`spec_sha256=None`。

#### 7.3.4 改动前后链路

```text
改动前：
  官方 test 元数据 → (seed, hard) ────────────────────────────→ 官方 robomme 环境（无 xhard0）
  test-hard/xhard{1..4}/specs.jsonl（V6，四段 seed）→ 条目 → gym.make(sampling_config, native_episode_spec) → robomme_hard 环境

改动后：
  官方 test 元数据 hard 子集 → xhard0 条目（seed 原值，difficulty="hard"，无 sampling_config、无 spec）→ robomme_hard 原生 hard 分支（评估：evaluation_hard.py）
  同一 xhard0 条目 → train_split_worker(builder_route=test-hard) 取 {seed, difficulty="hard"} → 官方 _worker 生成链（RobommeRecordWrapper + 规划器）→ H 侧 h5（生成）
  对照：xhard0_manifest.json → official._worker + robomme@1fadc0ec → O 侧 h5；robomme builder dataset="test" → 官方评估路线
  test-hard/xhard4/specs.jsonl（v7 母布局）→ 条目 → gym.make(sampling_config[xhard4], native_episode_spec)      → 全量回注（同现在）
  xhard4 母规格 + 白名单 → derive 信封 → gym.make(sampling_config[tier], native_episode_spec=信封)（阶段 4 派生，只 reset）→ 派生规格
  test-hard/xhard{1..3}/specs.jsonl（v7 派生）→ 条目 → gym.make(sampling_config[tier], native_episode_spec=layered) → L／N 点注入 + G 点冻结值
```

每一跳的观测键集合、形状、dtype 与现在完全相同（本方案不改任何观测、动作、控制模式；`RUNTIME` 四项不变）；xhard0 局的观测与官方同局逐字段相同是 12.222 §5 的零差验收对象，不由本文重复宣称。本链路无可训练参数。

### 7.4 接口：与 `scripts/README.md` 第 1 节逐条对照

| README 第 1 节的四处差别 | v7 |
|---|---|
| 换包 `robomme_hard.env_record_wrapper.BenchmarkEnvBuilder` | 不变 |
| `dataset="test-hard"` | 不变；每任务局数由 80 → 92（xhard4 独有三任务 20 → 32），16 任务合计 1100 → 1292 |
| `resolve_episode(ep) → (seed, tier)` | 不变；`tier` 取值多一个 `"xhard0"` |
| `make_env_for_episode(ep, max_steps=TIER_MAX_STEPS[tier])` | 不变；`TIER_MAX_STEPS` 增加 `"xhard0": 1300`（与官方 `evaluation.py` 默认相同，12.222 §3.2） |

`spec_binding(env)` 对 xhard0 局返回导出模式的 `{"available": True, "mode": "export", "spec_kind": "native-parity/1", "injected_mismatch": 0, …}`（环境里的 `SpecRecorder` 以导出模式存在，不是 `None`），对派生局多返回 `layout_hit`／`layout_overridden`／`layout_drift`；两个策略仓库把返回字典写进 info 的接法不变，但它们与合并脚本里「全部局都是 replay」的断言要按档分类（第一部分 §5 第 4 条）。`scripts/evaluation_hard.py` 的查表循环不改逻辑。

README 要改的只有数字与说明：第 1 节「换数据集」的局数、「多拿一个档位」加 xhard0、「步数上限按档给」加 1300；第 3 节表加 xhard0 列（与 hard 列逐字相同）；第 4 节链路改为「母布局抽签 → 派生 → 生成」三阶段与 v7 seed 规则；第 5 节对拍改为两条。

### 7.5 版本、文件与发布

- 包内 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl` 整体替换为 v7（schema `hard-specs/3`）；xhard0 不打包规格，builder 直接读官方 test 元数据（12.222 §3.1，读取时校验源文件摘要与 12 条／任务）。
- V6 的 `s4-setup-manifest.json`、`s4-to-delivery.json` 与 `scripts/configs/newtask-v6/v6-02/` 快照：v7 后失效，从工作树删除、git 历史保留（P1 允许删子目录内容；`configs/` 保留 `hard-parity-tolerances.json`）。`hard_regression.py` 的 `s4-subset`／`reset-replay` 子命令换成 v7 版（第二部分 §1.5）。
- `migrate_smvla_specs.py` 的 `check` 在 v7 后必然 FAIL（钉死 1100 与 `13x3x20+16x20`），删除该文件（历史迁移已完成、git 可取回）。
- h5 产物：v7 两次生成各 1100 局，落 `artifacts/newtask-v7/gen1/`、`gen2/`（v7 的 h5 不上传 bucket：gen1 留本机 `/data`，gen2 比完即删；公开 bucket `HongzeFu/robomme-hard-parity` 只放 O 侧与登记为 P 的段）；gen1 正式局保留在本机 `/data`，gen2 在 `PARITY_V7_TWICE=PASS` 留档后删除，只留逐局 sha 清单；v6 本机大产物已于 2026-09-28 按用户「直接全删」「确认删除 但是保网站内容」删除（约 2.19T、13054 个文件），只保留 site-v11／v12 引用的 281 个文件（36G）；xhard0 生成 h5（原话 13）：H 侧 192 局落 `artifacts/newtask-v7/xhard0/H/`，与 gen1 一样保留在本机 `/data`，`PARITY_O_H tier=xhard0` 通过后登记为 `parity-anchor-v7` 的 P 缓存；O 侧 192 局上传公开 bucket `HongzeFu/robomme-hard-parity` 段 `O-1fadc0e-a40/xhard0` 永久复用，本机副本读回 sha 一致后删除。

### 7.6 验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| xhard0 身份 | 官方 test 元数据 hard 子集 vs builder 条目 vs `xhard0_manifest.json`：任务、原 episode、seed、源文件 sha256 逐条相等 | 引入的恰好是原来的 192 个身份 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192 missing=0 extra=0` |
| xhard0 原生分支 | 捕获 `gym.make` 实参：`difficulty=="hard"`、无 `sampling_config`、无 `native_episode_spec`；`spec_binding` 为 `mode=="export"`、`spec_kind=="native-parity/1"`、`injected_mismatch==0` | 没有误入新值路径 | `XHARD0_NATIVE=PASS runtime_difficulty=hard mode=export injected=0 tasks=16` |
| xhard0 生成一致 | O 侧官方 `_worker`+`robomme@1fadc0ec` 与 H 侧 `robomme_hard` builder 路线各生成 192 局（A40、同驱动）；`compare --pair O:H --tier xhard0`；两侧 `identities.jsonl` 的 `recovery_mode` 逐局相等 | `robomme_hard` 生成 xhard0 的 h5 与官方生成器在容差内一致。容差比的是动作、关节／夹爪状态、RGB、帧数四项，不含深度与末端位姿，所以不能据此说整份 h5 一致；sha 相等数作参考 | `PARITY_O_H=PASS tier=xhard0 shape=16x1x12 compared=192 tol_over=0 both_fail=0` |
| xhard0 reset 层评估一致（判定） | 同卡两进程（官方侧只导 `robomme`）各 reset 192 局；确定性层逐位比（§1.5 `xhard0-reset-parity`） | 评估时两条路线建出的是同一场景 | `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0` |
| xhard0 演示层与策略层（只报告） | 演示帧与演示后状态的差异；每策略官方路线 192 局 vs v7 xhard0 192 局按 `(task, seed)` 对齐比 `status` 与步数 | 给出噪声量级，不作判定（D-16） | `XHARD0_DEMO_DIFF=INFO`；`XHARD0_EVAL_PARITY=INFO policy=<名> compared=192 status_diff=<n> steps_diff=<n>` × 2 |
| 白名单完整 | 阶段 1：16 任务 xhard4 导出 + 13 任务 × 3 档派生，共 55 局 trace；每条 `value()` 路径恰好匹配 L／G／N 一个模式，每个模式至少命中一次 | 闭世界成立：没有漏写、没有拼错 | `LAYOUT_WHITELIST_COMPLETE=PASS envs=16 traces=55 unclassified=0 unmatched_patterns=0` |
| 母布局共用 | 静态：xhard1～3 每行 `layout_parent.spec_sha256 == xhard4 同候选 spec_sha256`；每个 L 路径的值等于母值（列表取前缀、逐项路径取子集），每个 N 路径满足嵌套关系；**反向**：凡不在 G 表的 value 路径都等于母值，必需 L 路径缺席即 FAIL；四档 `seed` 相同 | 四档确实是同一批 20 个布局 | `V7_LAYOUT_SHARED=PASS tasks=13 layouts=20 tiers=4 rows=780 parent_mismatch=0 seed_mismatch=0 missing_l=0` |
| 前缀几何 | 静态：每个派生行按本档区域、最小中心距、OBB 规则逐对象重算 | 前缀在低档下合法，不依赖环境复核 | `V7_PREFIX_GEOMETRY=PASS rows=780 violations=0` |
| 交付集合 | 阶段 6 收尾：每任务各档交付的候选集合相同、每格 20 局 | 四档真是同一批布局交付，不是各档各自递补出不同候选 | `V7_DELIVERY_SET=PASS cells=55 per_cell=20 tier_set_equal=13` |
| 梯度定值 | 静态：13 环境 × 4 档的配置逐项等于 §3.2.2（单测）；动态：对每任务每布局，四档规格里的实际值等于该档定值、相邻档无维度下降、每步至少一维上升（`site/v6_tier_monotone.py --fixed`，VU／BU 含容器总数维度） | 每档只有一个数，且四档确实分开 | `V7_TIER_VALUES=PASS envs=13 tiers=4 mismatch=0`；`V7_TIER_FIXED=PASS cells=55 layouts=260 violations=0` |
| 目视总量梯度 | 对 Unmask／Swap／PickXtimes／SwingXtimes 每档取 1 局，桌面总数 = 内环 `layout.bins.*` 数 + `objects.distractors.placed`（count=0 时为 0，Swap 为外环数）或块数，与 §3.2.2「xhard1～4」列逐格相等；xhard0 列以 §3.2.1 实测为准 | 桌上看到的数量就是表里的数量 | `V7_VISUAL_COUNT=PASS cells=24 mismatch=0` |
| 步数余量 | 阶段 3 外推、阶段 6 用 gen1 全部 1100 局的 h5 执行步数（`frames − demo_frames`）逐格与 `TIER_MAX_STEPS` 比（§1.8） | 定值上调后评估不会被步数上限截断 | `V7_STEP_HEADROOM=PASS cells=55 over_90pct=0` |
| 回注零差 | 每格取 1 局经评估链 `make_env_for_episode` + `reset` 后 `spec_binding`：`injected_mismatch==0`、`layout_drift==0`，派生局 `layout_hit == len(layout_paths_hit)`，`unused==0` | 评估时建出的场景与生成时同一局 | `V7_RESET_REPLAY=PASS shape=13x3+16 injected_mismatch=0 layout_drift=0` |
| v6 回归 OPH | O、P 从 bucket 拉回并逐局核 sha；P = `parity-anchor-v6` 缓存（包绑定按登记来源判）；H = v7 HEAD 新生成（A40） | v7 没改变官方原生路径与 v6 回注行为 | `PARITY_ANCHOR=PASS`；`PARITY_O_P`/`P_H`/`O_H=PASS tier=native shape=16x3x3 compared=144 tol_over=0`；`PARITY_P_H=PASS tier=xhard shape=13x3x3+16x3 compared=165 tol_over=0` |
| v7 两次生成一致 | gen1 由 `generate_h5 --mode continue` 出正式局并写 `delivery.json`，经 `import-delivery` 登记；gen2 由 `hard_parity.py generate --side H2 --tier v7` 在另一占位 job（同型号 A40、同驱动）按清单重放；`compare --pair H:H2 --tier v7` | 规格 → h5 的映射确定，只剩 RRT 墙钟噪声 | `PARITY_V7_TWICE=PASS shape=13x3x20+16x1x20 compared=1100 tol_over=0`（`sha_equal` 作参考） |
| 官方冻结 | `upstream_guard.py check --require-upstream`；三入口与录像器零 diff | 基线没被改写 | `UPSTREAM_GUARD=PASS` |
| 入口冒烟 | `hard_regression.py eval-smoke --task BinFill --episode 0`（xhard0 局，`mode=export`）与 `--episode 12`（xhard1 局，`mode=replay`） | 评估入口两类局都能起 | `HARD_EVAL_SMOKE=PASS episodes=2` |

为什么这些判据能成立：身份类判据是纯静态集合比对；`V7_LAYOUT_SHARED`、`V7_PREFIX_GEOMETRY`、`V7_DELIVERY_SET` 比的是规格与清单文件，不依赖运行；`LAYOUT_WHITELIST_COMPLETE` 靠闭世界（R10）把「漏写」从静默变成报错，再用动态 trace 逐模式确认命中；回注零差靠 `SpecRecorder` 的「抽一次核随机流、用冻结值」机制（§7.3.2），同代码同 seed 的 CPU 随机流是确定的，所以 `layout_drift` 要求逐位为 0；`XHARD0_RESET_PARITY` 只判演示回放之前的确定性部分，演示受墙钟噪声影响，放在报告层；两条生成对拍在同型号同驱动 A40 上做，这是 §7.8 说明的逐位边界，所以才允许把 `sha_equal` 当参考数、把容差当判定。

### 7.7 parity 锚点实现细节（D-11～D-13）

**三侧定义**（`hard_parity.py` 的 `SIDES` 为 `O／P／H` 加 v7 两次生成用的 `H2`（§1.5），O／P／H 三侧的含义改为下表）：

| 侧 | 来源 | 生成频率 | 存放 |
|---|---|---|---|
| O | 官方 `1fadc0ec` worktree + vendor `_worker` | 只生成一次（阶段 4 已有 O-native 144 局，A40/595.71.05） | 公开 bucket `HongzeFu/robomme-hard-parity` 段 `O-1fadc0e-a40/native`（148 对象，12.213 读回 sha 全等）；本机副本已清空，比对前按需拉回 |
| P | `git tag parity-anchor-*` 指向的 commit | **不重跑**：复用该 commit 作为 H 时的已验证产物 | 缓存登记表 `docs/validation/parity-anchors.json`（新文件）；`parity-anchor-v6` 的 P 缓存即 bucket 段 `H-34a1cea-a40/native`（144）与 `H-b1afc80-a40/xhard`（165）；`parity-anchor-v7` 另登记 `xhard0`（192，本机 `artifacts/newtask-v7/xhard0/H/`）与 `v7`（1100，gen1） |
| H | 当前 HEAD | 每次修改后生成 | `artifacts/newtask-v7/parity/h5/H-<tier>`，上传 bucket 时段名 `H-<短sha>-a40/<tier>` |

**缓存登记表** 每条：`tag`、`commit`、`tier`、`h5_root`（bucket 段名与本机拉回路径）、`identities_sha256`（逐局 sha 清单的哈希）、`gpu_model`、`driver`、`generated_at_commit`（产物实际生成时的 src_commit）、`source_side`（产物当年是作为哪一侧生成的，`parity-anchor-v6` 的两段都是 `H`）、`worker`／`env_module`（取自当年的 `identities.jsonl`）、`equivalence`、判定行原文。`hard_parity.py compare` 取 P 侧前先核：tag 解析出的 sha == 登记 `commit`、逐局 sha 重算相等、GPU/驱动与 H 侧相同；任一不符 → `PARITY_ANCHOR=FAIL`，不比。**P 侧的包绑定**：`_binding_ok("P", …)` 现在要求官方 `_worker` 与 `robomme`，而锚点产物当年是 H 侧（`train_split_worker.run_one`、`robomme_hard`）生成的，照旧会全判不绑定；改为按登记表的 `source_side`／`worker`／`env_module` 判——与登记一致即绑定，不一致即 FAIL。

**等价核验判据（`equivalence`，阶段 0′ 与 `parity-anchor-v7` 共用）**：tag commit ≠ 生成 commit 时，对 `git diff <生成> <tag> -- src/robomme_hard scripts/parity scripts/injection-dev pyproject.toml uv.lock` 逐文件归类，只允许四类：①文档与注释；②导入路径（模块搬目录后的 `sys.path`／import 改动）；③不触及产物字节的外围逻辑（输出目录「已跑过」的判定、上传与读回、比对时补读字段）；④生成路径之外的新子命令。任何一处改动落在「环境构造 → 规划 → 执行 → 录像落盘」链路上即判 `content_affecting`，不打 tag、停下找用户。`parity-anchor-v6` 的预审（`34a1ceab`→`ce3843b4` 15 个文件、`b1afc804`→`ce3843b4` 14 个文件）：`_rollout.py` 是输出目录判定放宽，`train_split_*`、`__init__.py`、`site/*` 是 `seed_layout` 移目录后的导入路径，`hard_parity.py` 是 bucket 上传白名单修复与比对时补读 `robomme_module`，`hard_specs.py` 只改一行注释，其余为 README——均属①～③。`parity-anchor-v7` 的 gen1 与 xhard0 H 侧在阶段 5′／6 起跑时 HEAD 精确等于所跑代码（§6），到阶段 8 打 tag 之间的差异只允许是换包（包内规格文件）与文档，换包那一处单独登记为「规格落包、生成时经 `ROBOMME_HARD_SPECS_ROOT` 读同一份文件」，并核两份规格文件 sha 相等。

**「验证过就不再验证」的边界**：只省去重新生成 O 与 P；每次改动后的 H 必须新生成并按档比对（native 三对、xhard 只有 P:H、xhard0 首次只有 O:H）。锚点 tag 一经打上不移动、不删除（tag push 到远端）。

**判定行**：`PARITY_ANCHOR=PASS tag=parity-anchor-v6 commit=<sha> cached=144+165 sha_bad=0 gpu=A40 driver=595.71.05`；`PARITY_O_H tier=xhard0 shape=16x1x12 compared=192 tol_over=0`（首次，无 P 侧）；`PARITY_O_P`／`PARITY_P_H`／`PARITY_O_H tier=native shape=16x3x3 compared=144 tol_over=0`；`PARITY_P_H tier=xhard shape=13x3x3+16x3 compared=165 tol_over=0`。

### 7.8 容差数值与跨卡探针原文

**结论先说**：现行容差只有一套，标定自**同型号（A40）、同驱动、不同节点**的 O:P 144 对，**不是跨 GPU 型号的容差**；跨型号只做过 1 条身份的逐位探针，结论是「逐位一致只在同型号 + 同驱动内成立」，跨型号的容差判据至今没有标定。

权威配置 [`scripts/configs/hard-parity-tolerances.json`](scripts/configs/hard-parity-tolerances.json)，消费者 `hard_parity.py::pair_metrics`／`calibrate`／`cmd_compare`：

| 指标 | 阈值 | 比较的量 |
|---|---:|---|
| `action_max_rad` | 0.041265913943240015（≈2.36°） | 共同时间步内 `action/joint_action` 全分量最大绝对差 |
| `state_max` | 0.04113650321960449 | `obs/joint_state` 与 `obs/gripper_state` 最大绝对差（混合字段，不能统一称米或弧度） |
| `image_mad` | 1.0 | 0～255 RGB 逐像素绝对差先逐画面平均、再两相机与共同时间步平均（不是逐像素上限） |
| `frames_max` | 5 | 两侧时间步数之差 |

公式 `阈值 = max(观测最大差 × 1.5, 下界)`，帧数先向上取整；下界 0.005／0.005／1.0／5；「合理性上界」0.05／0.05／10／200 检查的是**原始最大差**、超了只让标定 FAIL，不截断阈值。标定数据：O（gl1517，job 62126060）与 P（gl1504，job 62126061），均 A40、驱动 595.71.05、16 worker；144 对里 143 对逐字节相同，唯一非零的一对是 `PickHighlight/hard/seed 12300` 从第 549 步起分叉（动作最大差 0.0275、图像平均差 0.144、帧数相同），O 与 H 在该身份上逐字节相同，报告归因为 P 侧那次运行的 RRT 墙钟噪声（`docs/validation/newtask-v6/hard-split/stage4.md`「容差标定」）。所以：阈值 = 0.0275×1.5、0.0274×1.5，图像与帧数取下界。

**为什么它不是「多卡」容差**：[`20260927-cross-hardware-probe.md`](docs/validation/newtask-v6/hard-split/20260927-cross-hardware-probe.md) 用同一条身份（BinFill/ep0/seed 4000/easy）在四张卡上跑官方 A 路：A40 两个节点 sha 相同；RTX 6000 Ada（本机）vs RTX A6000（aspen）只有 16 个 `joint_action` 值差 ≤ 2.24e-18；**Ada vs A40 从第 7 步起全面分叉**：`joint_state` 最大 0.029 rad、`eef_state` 0.0377、`front_depth` 最大 2.67e3、RGB 逐像素最大 211～235。这说明 0.029 rad 的跨型号状态差已到 0.041 阈值的约七成（该探针里型号与驱动大版本同时不同，没有拆开归因），且图像逐像素差远超 1（`image_mad` 是平均值，单局是否超 1.0 未算），跨型号数据没有进过任何标定。因此 D-9 要求 v7 两次生成都在 A40 上做；本机 Ada 与 aspen A6000 只用于冒烟与静态验收，不产正式对拍数据。

另有一个容易混淆的数：`hard_specs.py::RECORDED_FLOAT_TOL = 1e-5` 是回注校验里「只记录不回注」的浮点观测点允许的漂移，与轨迹对拍容差无关；派生局的 `layout_drawn` 核随机流**不用它**，要求逐位相等（§1.2）。

## 8. 审计意见处置对照（第三次修订）

审计来源：Codex 两轮（锚点 `43c4f83f`、`eb929364`，会话记录只读取回）、Claude 两轮（锚点 `43c4f83f`、`a90efc0f`；第二轮由 3 个只读 sonnet 子代理核查、主会话抽查源码）。第二轮把两边合并去重为 M1～M50（延续问题）与 N1～N19（针对 12.230／12.231 新增内容）。下表按「问题 → 处置 → 落点」列出；标「用户定」的四项见原话 23。

| 编号 | 问题（一句话） | 处置 | 落点 |
|---|---|---|---|
| M1 | BinFill 低档独立重抽投入，超过母布局摆放数即派生失败（估算三档联合存活约 28%） | 用户定：嵌套派生 | D-15、§1.8、§1.3 |
| M2、M6 | UnmaskSwap 分层回注时 `same_geometry` 必抛错；交换规划落在注入前的布局上 | 分层模式改核 `layout_drawn`；注入后重新规划；冒烟覆盖 | §1.8、第一部分 §6 阶段 3 |
| M3 | 白名单漏写会静默当 G 处理，四档不共用而闸门全过 | 闭世界 + 动态核对 + 反向核对 | R10、§1.3、§7.6 |
| M4 | `native_layout_parent=` 无处接收，`SpecRecorder` 新签名不兼容 | 改为 derive 信封，签名不变，环境文件不改 | §1.2、§1.4 |
| M5 | `native-layered/3` 被 `spec_kind` 校验拒绝 | 接受集合按难度族放宽 | §1.2 |
| M7 | 「回注会二次复核」说法过强 | 改写，并加离线 `V7_PREFIX_GEOMETRY` | 第一部分 §3.2.3、§7.3.2、§7.6 |
| M8 | VideoRepick 规格里没有 `layout.button_xy` | 删去 | §1.3 |
| M9 | 抽签上限不够凑满 30 候选 | 用户定：VideoPlaceButton、VideoRepick 提到 100 | D-17、§1.4、§2 |
| M10、M38、M47 | 四档交付集合无校验；只有 xhard4 的任务递补条件字面为假；MoveCube 分层选签 | 候选池单写者 + `V7_DELIVERY_SET`；三任务单独条件；验收不按编号写死 | §1.4、§7.6 |
| M11 | `layout_injected` 定义与判据矛盾 | 拆成 `layout_hit`／`layout_overridden`／`layout_drift` | §1.1、§7.6 |
| M12 | 生成时「回注」与「worker 里派生」两处冲突 | 生成只回注，派生只在 `derive_specs.py` | §1.5 |
| M13 | 身份键常量加新键会改变 v6 规格摘要 | 身份键按 schema 分表 | §1.1 |
| M14 | 阶段 3、7 只能读包内规格 | 规格根覆盖 `ROBOMME_HARD_SPECS_ROOT` | §1.1、§3 |
| M15、M16、M17、M19 | gen1／gen2 绕开 `hard_parity.py`；gen2 参数与交付清单不存在；v7 清单缺 `episode`、v6 xhard 165 局命令缺失、native H 缺 `--src-root`；比对目录写死 v6 | gen1 写 `delivery.json` + `import-delivery`；gen2 经 `generate --side H2 --tier v7`；目录参数化；补齐 runbook | §1.4、§1.5、§3 |
| M18 | P 侧绑定按官方 `_worker` 判，会把锚点产物全判不绑定 | 按登记表的生成来源判 | §7.7、第一部分 §4.1 |
| M20 | 磁盘口径过时（815G） | 更新为 2.8T 并补同时驻留大头与停止阈值 | 第一部分 §5 |
| M21 | 阶段 0′ 缺 bucket 拉回与逐局核 sha；§7.5 残留「计费拒绝」 | 补命令与判据；改写 §7.5 | 第一部分 §6、§3、§7.5 |
| M22 | 锚点等价判据未落地，tag 与生成 commit 不同 | 写死四类允许差异与预审结论 | 第一部分 §4.2、§7.7 |
| M24、N12 | xhard0 的 `spec_binding` 实为导出模式；条目缺 `row`／`runtime` | 全文改为 `mode=export`；条目补两键 | §1.1、§1.5、§7.4、§7.6 |
| M25、M26、M27、M28 | 策略侧对 xhard0 缺 `candidate`、绑定只认 replay；分片按旧公式；`srun` 仍 1 CPU；视频完成判据对不上 | 逐身份清单分片、绑定分类、步骤 4 CPU、按策略认终态记录 | 第一部分 §5、§3.1 |
| M29 | 预算缺合计与漏项 | 补三类合计行与阶段 1、3、7 各行 | §2 |
| M30、N18 | 评估 job 数量与规格的出处 | 注明沿用 12.212 授权与原话 11，合计 11 个在线 | 第一部分 §5 |
| M32～M37、M39～M46、M49、M50 | 乘式、`unused` 口径、`layout_drawn` 容差、对象描述、匹配语义、锁定清单落点、键名与 seed 公式、`configs` 取回、容差外推分流、按档比对对数、跨卡归因、交叉引用、策略分支、HDF5 比较范围、gen2 删除前冻结 | 逐条改写 | 散见各节 |
| M23、M31 | xhard0 零差验收、预算阶段号 | 前几轮已修 | — |
| M48 | 区间单调判据 | 被定值判据取代 | §1.7、§7.6 |
| N1 | 第 4 干扰色加进共用三色池，会让 v6 Unmask／Swap 回放报错、随机流漂移 | 另设 `BLOCK_DISTRACTOR_COLORS` | R11、§1.7、第一部分 §3.2.2 |
| N2 | R3「v6 值仍可从源码提取」与「就地改常量」矛盾 | v6 值以包内 header 为唯一存放处，另冻结快照文件；补五个 `native_blocks` 与 `RELEASE_NOTES` | R3、§1.5、§1.7 |
| N3 | 「PickXtimes xhard 分支漏改」前提不存在，照做会改坏原生 hard | 删去该行 | R12、§1.7 |
| N4 | 策略层「终态全同」判据不成立 | 用户定：环境层判、策略层只报告 | D-16、第一部分 §2、§7.6 |
| N5 | Unmask `count=0` 在 `parse_distractor_cfg` 即被拒 | 放宽为 `count<0`；视觉计数改读 `objects.distractors.placed` | §1.7、§7.6 |
| N6 | `V7_TIER_FIXED` 在 VU／BU 的 hard→xhard1 必报 `flat_step`；「严格递增」自相矛盾 | 语义改写，加容器总数维度 | §1.7、§7.6 |
| N7 | 定值表 xhard0 列来源混用、步长列与七／八处计数 | 表不动，加读法补注 | 第一部分 §3.2.2 |
| N8 | 漏列必须同步改的现有单测与工具 | 补全清单 | §1.7 |
| N9 | 步数上限余量（审计原稿「已超限」用的是视频帧数口径，更正为按 h5 执行步数核） | `V7_STEP_HEADROOM` | §1.8、§7.6 |
| N10 | reset 层逐位要求与 RRT 墙钟噪声矛盾 | 分确定性层与演示层 | §1.5、第一部分 §2 |
| N11 | runner 身份复核会拒绝 xhard0 | 新增 `test_metadata` 来源 | §1.5 |
| N13～N17、N19 | parity 接线遗漏；「只差包名」说法；`both_success` 硬条件；D-8 未吸收 xhard0；10′ 准备与字段名；陈旧文字 | 逐条补写 | §1.5、§3、第一部分 §2、§4、§5、§7.1、§7.2、§7.3.2 |
