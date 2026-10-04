> **本方案是四个模型接入本仓库评估链路、并按三档闸门在 Great Lakes 跑完的完整计划。** 2026-10-04 按用户新口径整篇重写，取代此前「两模型、每 job 串行、原入口必须完全一致」的版本（旧版见 `git show 25f4fe6b:1003-oracle-subgoal-groundsg-eval-plan.md`）。本轮只改本计划文件；代码、下载、作业、评估都要等用户确认本计划后才开始。
>
> **锚点**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，规划依据 `cfcc302c`。第三方锁定：MME-VLA 子模块 `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`；PonderPounce `723df35762bb641e1d520e4fa9359b98644adc21`；vla-eval PyPI `0.7.0`；Astra-on-RoboMME `4c3fd6a8667e7a219e547fe1a533a4b9726fc6db`；官方环境 `856bc3a189d4172f3f47dbee4424d585f8d78db3`（其 `src/robomme` 与本仓库、与对拍锚点 `1fadc0ec` 逐字节相同）。提交编号沿用 `12.<小版本>`。
>
> **用户原话（2026-10-04，按时间顺序）**：
> 1. 「我需要加入3档的闸门对拍 https://worv-ai.github.io/ponderpounce/ 这个也要移植 第一档 改完重新生成任务 需要和原本一致 第二档用原版代码库接口 测试 vs 用改完的接口 测试 xhard0 一致 第三档 开始进行新的真正的xhard eval」
> 2. 「用户完整确认之后再开始写代码。」
> 3. 「所有的测试都在gl上进行。」
> 4. 「第二档报告不阻塞结论。」
> 5. 「你告诉我接线增加hard0会增加哪些内容同时现在改完之后1300步 1600步都要对应好,hard0都是一千三百步 新的都是一千600步。」
> 6. 「把所有的查表功能都去掉。……都是只在这里留一个接口。」（附官方 `BenchmarkEnvBuilder(..., max_steps=1300)` 写法）
> 7. 「照官方（我推荐）：允许第 1301 步，与原版接口行为相同……确认」
> 8. 「改完之后在本机器上测一个episode然后测出CPUmemory和GPU的显存占用如果有超过占位job的需要重新启动job反正就是在本机先做好测试不要上了集群的J0B之后再报错。」
> 9. 四项「这些都同意」：V9 保留执行满 1600 步即记超时、数值取 builder 的 `max_steps`；PonderPounce 第二、三档都跑；放行下载 `worv-ai/ponderpounce-9b-robomme` 到 NFS；第一档按噪声基线口径。
> 10. 「做好并行可能性的评估尤其是第一、第二、第三档是否都可以并行来做。」
> 11. 「写入计划第一部份整合成一个比较粗略的内容。就像我刚才问你的完整流程一样这样就足够了第二部分你所有的细节都要到位你可以使用SubAgebt来确定细节。」
> 12. 「评估一下保存视频需要多大保存压缩后的视频」「把所有的保存视频都改为压缩视频是否可以就是现在的对拍完全靠Xhard0来实现。」
> 13. 「https://github.com/bingaochen/Astra-on-RoboMME把这个也加在一起测了但是这个因为要调用GPT-6Astra的API你要先测试联通性先把API存下来然后只跑原接口和现接口XHARD0 16*1 个 总共32次」
> 14. 「所有使用Astra的你要严格让用户审批episode的数量 包括本机的测试等」
> 15. 「预检测结束之后再申请。reatlakes占用的J0B按照所有预检测之后的占用的并集合如果有些需要两张卡才能跑起来的。单独给他申请job不要和其他的混起来。你最多占用10张卡你自己来分配。」
> 16. 「批准Astra本机御检两局。如果失败可以增加到6局。如果6局配额用完了还失败就停止。继续做其他任务」
> 17. 「我在授权你用Astra跑新的xhard12345 只跑1局 确保接口通畅」；后经确认「Astra V9 合计1局」
> 18. 「你的第二档和第三档同时放量为什么要这么做因为你总共只有十个GPU而且你的Job可能是固定的？」「生成对拍和每个席位的第二档都要优先跑。然后再开始跑第三档」
> 19. 「你还需要确认Xhard0是一千3。新的XHARD是1600。然后你要在预检的时候确认视频都能保存」
> 20. 「第一档和第二档都不要阻塞第三档的生成就是第一档和第二档有任何不同的结论都不要停只作为用户最后决策项。一路跑到尾。」（覆盖第 1 条里第一档作为硬闸门的读法）
> 21. 「都同意，Astra V9 合计1局 不要改代码十四十五十六十七你自己来决策。都可以直接跑用户只规定你最多用十个gpu尽可能的早点开始占用卡尽可能的复用一个4十八小时等待的job」
> 22. 「不要现在开始计划！！！」「你现在只负责改计划」——计划与预算已同意，但开工要等用户下令。
> 23. 「Astra只设置一个金额的上限。测试冒烟和实际跑都是30dollar」
> 24. 「所有的开工都是要我明确确认无歧义的说开工。任何其他都不能作为开工条件 这个写入agentmetarules」（已写入正本第 2 条，`3fe9c80`）
> 25. 「现在的GPU需要排队尽可能高效利用而且排队排到了你需要叫醒Agent。」「我现在说的是唤醒Agent这个设计是写在计划里不是现在直接进行」
> 26. 「12项目其他的都同意放行。」——对 2026-10-04 两份审计（本会话 workflow 与 Codex）合并出的 12 项决策，除 Astra 上限按第 23 条外，其余按执行方推荐放行；逐项见第一部分第七节。
> 27. 「再加入一个要求如果本机预检完成之后还是没有卡可以在本机跑第二档就是Xhard0的两侧 但是gl仍然要做全流程」（对第 3 条「所有的测试都在gl上进行」的补充：本机多跑一遍第二档，不替代 GL）
> 28. 「本机做完第二档之后第一档也要做。优先第二档」
> 29. 「用户修改了要求本机第一第二档都要做先做第二档再做第一档 gl第二第三档都要做还是按照老顺序」「astra本机先不做 只做本机冒烟」
> 30. 「就算已经排到卡了本机的第一第二档也要做」——第 27 条里「还是没有卡」的条件取消：本机的第二档、第一档无条件做。执行方对第 27、29 条的理解：GL 仍做全流程（第一档占一席、各席第二档接第三档），本机这一遍是额外的。
> 31. 「那就在本机先做第一档。旧代码和新代码的生成。然后给一个粗信号然后再做第二档全量的所有除了Astra。gl还是这三档不要不动。越早拍到越早开始」——覆盖第 28、29 条里本机的先后顺序：本机先第一档（旧、新代码各生成一遍），后第二档。此前执行方已说明：本机新代码对 A40 基线比没有意义（判定工具前提是 A40，差异分不清是代码还是显卡），所以本机第一档改为同机旧码对新码。
> 32. 「本机的动作也不要有任何阻塞」
> 33. 「第二档你所有的model都要跑!!!!!」；执行方说明本机驱动不够、给出三条路后，用户定「按A做，本机不含Astra」——本机另建一个只换 CUDA 构建的环境跑 PonderPounce。
> 34. 「现在的SubAgent只能只负责改代码吗?是否可以让SubAgent也负责启动长任务，启动长任务的SubAgent也需要使用Opus。」「放开运行子代理 同步agentmetarules」（已写入正本 `CLAUDE.md`「运行型子代理」，`5697d96`）
>
> 沿用的更早决定：「不要下载」已被第 9、13 条对 PonderPounce 权重与 Astra 的放行覆盖，其余资产一律用本机已有副本；「我只关心怎么去改现在的这个 repo，让它和官方的这个 evaluation 是对齐的」仍是接线原则——不改任何第三方模型实现。

# 第一部分（给人看）

## 一、目标

在本仓库接好四个模型的评估，新增 xhard0 独立入口，删掉步数查表，然后按三档闸门在 Great Lakes 上跑完。

| 模型 | 来源 | 第二档（xhard0 原版对改后） | 第三档（V9 正式评估） |
|---|---|---|---|
| GroundSG + Oracle | `third_party/mme-vla` 已有实现 | 16 任务 × 1 档 × 12 局 = 192 局，两侧各一遍 | V9 全量 800 局 |
| GroundSG + QwenVL | 同上 | 192 局，两侧各一遍 | 800 局 |
| PonderPounce | 新引入，官方仓库加 27 GB 权重 | 192 局，两侧各一遍 | 800 局 |
| Astra | 新引入，调用付费的 GPT-6 Astra 接口 | 16 任务 × 1 档 × 1 局 = 16 局，两侧各一遍，共 32 局 | 不做正式评估，只用 1 局确认 V9 接口通 |

V9 的 800 局 = `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50`（任务与档的对应见 `hard_specs.py::_v9_cells`）。

## 二、已定口径

1. **三档**：第一档生成对拍、第二档 xhard0 原版对改后，都只出结论、不阻塞；无论结论如何都一路跑到第三档结束，两档的结论作为最后交给用户的决策项。第三档是正式评估。
2. **全流程在 GL 跑，本机另跑一遍第二档和第一档**：本机做改码后的纯 CPU 短测和上集群前的预检；预检做完后，不管 GL 有没有排到卡，本机两张卡都先跑第一档（旧代码、新代码各生成一遍，给一个粗信号）、再跑第二档全量（除 Astra 外的模型）。GL 照原顺序把三档从头到尾跑一遍，哪个席位先排到就先开始，成绩与标注以 GL 为准。Astra 在本机只做预检冒烟。
3. **步数上限只有一个入口**：创建 `BenchmarkEnvBuilder` 时传 `max_steps`，xhard0 传 1300，V9 传 1600；按档查表全部删除。
4. **xhard0 的结束方式照各模型的官方循环**；V9 保留「执行满 1600 步即记超时」。
5. **落盘的画面只有压缩视频**；第二档对比靠每步的状态、动作、文本和画面哈希，不保存原始画面。
6. **Astra 的局数逐项审批，费用只设一个金额上限**：已批 GL 上 32 局、本机预检 2 局（失败可加到 6 局，用完仍失败就停掉 Astra）、V9 接口连通 1 局；其余一律不跑。预检与正式运行合计花费不超过 30 美元，到线即停 Astra，其余模型照常。
7. **占位 job 尽早申请、尽量复用**：让排队和改代码同时进行；同一批 48 小时占位 job 从头用到尾。规格和数量由执行方自定，同时在用最多 10 张卡；需要两张卡的模型单独申请，不与别的模型同时混用。到期没跑完允许续交同规格 job，只跑未完成的局。
8. **开工只认用户明确说「开工」**：计划获批、预算获批、卡排到，都不是开工条件。说「开工」之前不改代码、不下载、不运行、不挂监听。
9. **第二档与第三档逐席衔接**：每个席位先跑完本席的第二档，再接本席的第三档；不等其他席位。
10. **成绩怎么标在开跑前写死**（见第五节），不看完分数再定标准。
11. **排到卡要叫醒执行方**：开工后挂一个盯排队的后台任务，任何占位 job 开始运行就唤醒会话，立刻往这张卡上派活（设计见第二部分五）。

## 三、流程

**第 0 步：占位 job 与唤醒**

- 8 个单卡席位加 1 个 Astra 专用的两卡 job，共 10 张卡，已在排队（2026-10-04 误提交后经用户同意保留）。
- 组里的配额是 20 张卡共用，实际能拿到几张取决于其他人的占用；拿到几席就先用几席，不等齐。
- 48 小时从 job 实际拿到卡起算。说「开工」之前卡先到了，执行方不会动，这段时间会空转；这是「开工只认明确指令」的已知代价。
- 开工后挂上盯排队的后台任务：有 job 开始运行就唤醒会话，往这张卡上派当时能跑的活。

**第 1 步：接线（只改本仓库，不动 `src/robomme/`，不改第三方源码）**

- 新增数据集 `test-hard0`，只含 xhard0 的 192 局；默认的 `test-hard` 仍是 V9 的 800 局。
- 删除步数查表，评估链路的步数从启动命令一路传到 builder。
- GroundSG 两组：加一个适配器，在本仓库的环境上运行官方单局循环和官方预测器。
- PonderPounce：加一个按它的协议收发的客户端；它的模型服务原样使用。
- Astra：加一个驱动，把它的原循环接到本仓库的 builder 上。
- 每个模型另加一个「原侧」驱动：用模型原版代码加官方环境，只跑 hard 的那些局。
- 录像逐局转成压缩视频后才同步；清单、报告、对比工具按新的数据集和模型扩展。

**第 2 步：本机预检**

- 每个模型的每条路线在本机跑通 1 局，测 CPU 内存峰值、显存峰值、单局耗时。
- 确认步数上限：xhard0 是 1300、V9 是 1600。既核对每条路线从启动命令到 builder、到发给模型的数值，也各用 1 局不加载模型的空动作跑到顶，看实际停在第几步。
- 确认每条路线（含原侧）每局都存下了压缩视频，能完整解码，帧数与步数对得上。
- 某条路线报错：修好后重跑，每条路线最多另跑 2 局；用完仍不过就停这条线并记入决策项，其余路线照常上集群。
- PonderPounce 的官方环境要求显卡驱动不低于 580，本机是 570：本机用只换 CUDA 构建的环境做预检；GL 上的官方环境另在 GL 节点跑 1 局确认能加载。
- 内存超出已申请席位的规格：只对放不下的那个模型另交更大的 job，其余席位照用。显存超过单张 A40：该模型改用单独的两卡 job。

**第 2.5 步：本机先跑第一档，再跑第二档（无条件做）**

- 时点：本机预检做完就开始，不看 GL 有没有排到卡；GL 排到卡后两边各跑各的，互不等待。
- 先第一档：在本机用旧代码和新代码各生成一遍 V9 每格 3 局（129 局）和 xhard0 每任务 3 局（48 局），两遍逐局互相比。不拿 GL 的噪声基线比：那份基线是 A40 上做的，本机显卡不同，差异分不清是代码还是显卡。
- 这只是粗信号：本机没有自己的噪声基线，偶发抖动的局分不清是噪声还是回归；两遍完全一致可以放心，有差异的局只列出来，等 GL 的第一档定性。
- 后第二档：GroundSG 两组在 xhard0 上跑原侧和新侧，各 192 局，两张卡各跑一个模型。PonderPounce 也跑，原侧和新侧各 192 局，排在先空出的那张卡后面：它的官方环境要求驱动不低于 580、本机是 570，所以本机单建一个环境，torch 版本号不变，只把 CUDA 13 构建换成 CUDA 12 构建，两侧都用这个环境；GL 上照旧用官方环境。Astra 不跑。
- 本机这两档同样不阻塞任何事（原话第 32 条）：第一档有差异不拦本机第二档；本机任何结论都不拦 GL，GL 也不等本机。某条线在本机起不来就跳过、记入决策项，下一条照跑。
- 本机的结果单独成表，标「本机结果」；不替代 GL 的第一、二档，也不影响成绩标注。

**第 3 步：GL 第一档，生成对拍（只出结论，不阻塞）**

- 用改完的代码重新生成 V9 每格 3 局（43 格 × 3 = 129 局）和 xhard0 每任务 3 局（16 × 3 = 48 局），与噪声基线比。
- 占 1 个席位约 45 分钟；其余席位在每条路线 1 局 smoke 通过后直接开始第二档，不等第一档跑完。
- 不一致不停：照常往下跑，结论（哪些局不同、定性是噪声还是回归）记入最后的决策项。
- 不一致的局要新旧代码各重跑一遍来定性，重跑预算共 20 局：先给 V9，剩下的给 xhard0，排不上的标「未定性」。

**第 4 步：GL 每席先跑第二档，跑完接第三档**

- 第二档：每个模型在 xhard0 上跑原侧和新侧，同一身份的两侧放在同一席、同一张卡上先后跑；差异写进报告，不拦第三档。
- 第三档：GroundSG 两组和 PonderPounce 各跑 V9 的 800 局，按身份清单切到多个席位。
- 卡数固定为 10 张，两档同时跑并不更快；每个席位的队列里第二档排前面。一个席位跑完本席的第二档就自动接第三档，不等人，也不看第一档、第二档的结论。
- 借去跑第一档的那个席位，跑完生成后再补它的第二档分片。
- 这样两档的结论先出来；即使有差异也不叫停，留到最后一并交用户决定。
- Astra 只跑第二档的 32 局，外加 V9 的 1 局连通确认。跑完后它的两张卡借给其他模型跑第三档，不与 Astra 同时运行。
- 48 小时到期没跑完：续交同规格的 job，只跑未完成的局；到期被打断的局不算故障重试。

**第 5 步：交付**

- 每个模型的成绩表（V9、新入口 xhard0、原版入口 xhard0）、第二档差异表、全部压缩视频、留档。
- 产物搬回 `/data`，NFS 不留大文件，按清单释放自己的 job。

## 四、并行安排

| 组合 | 结论 |
|---|---|
| 第一档与第二档 | 同时跑：第一档占 1 席，其余席位直接跑第二档。 |
| 第一档与第三档 | 第一档排在前面，但第三档不等它的结论。 |
| 第二档与第三档 | 不分两拨同时跑（卡数固定，不会更快）。每席先第二档后第三档，自动衔接。 |
| 模型之间、同一模型的分片之间 | 同时跑。单卡席位同规格，可以在模型之间调配。 |
| 同一身份的原侧与新侧 | 不并行，同席同卡先后跑。 |
| 写代码、拷资产、建环境 | 同时进行。 |
| 本机与 GL | 同时跑。本机先第一档（旧码对新码）后第二档，GL 照原顺序做全流程。 |

## 五、怎么算完成

| 项目 | 判据 |
|---|---|
| 接线 | 两个数据集不串、默认 V9 不变；步数只来自启动命令；本机短测通过 |
| 预检 | 每条路线跑通 1 局，有内存、显存、耗时数字；步数上限实测为 xhard0 1300、V9 1600；每条路线的压缩视频存在且可解码 |
| 第一档 | 两个集合都跑完并出判定行；PASS 与否如实报告，不影响后续 |
| 第二档 | 两侧身份齐全，差异表生成；判定为 `INFO` |
| 决策项 | 第一档、第二档的全部结论汇成一节交用户，由用户决定是否补跑 |
| 第三档 | 每个模型 800 局都有唯一终态，无缺失、无重复；视频齐全可解码 |
| 预算与收尾 | 局数不超过第二部分的预算表；Astra 花费不超过 30 美元；job 与临时文件按清单清理 |

**第三档成绩的标注（开跑前定死）**

| 情形 | 标注 |
|---|---|
| 第一档 PASS，且该模型第二档两侧身份齐全 | 正式成绩 |
| 第一档 FAIL，或有局因重跑预算不够而「未定性」 | 正式成绩，生成等价性未验证 |
| 第一档 INVALID（缺身份、缺结果、比较前提不成立），或该模型第二档不完整 | 探索性结果 |

- GroundSG 的第二档只读三样：成功率、终态分布、每次起服务后第一局的逐步轨迹。它的模型服务随机数跨局累积，某一局分叉后同一服务上后面的局都会错开，后面的逐步差异不归因于接口。
- QwenVL 与 Astra 只比成功率和终态分布；不给 QwenVL 加「同侧跑两遍」的基线。
- PonderPounce 两侧都用 GPU 渲染，成绩不对照论文数字。
- 第一档若判回归，第三档修复后重跑不预先授权，到时另定。
- 第一档 PASS 只说明生成链路没变，不说明新的 xhard0 入口正确；后者靠接线测试和第二档。

## 六、子代理分工与合并（简述）

代码按文件切成七块交给写入型子代理，各自在独立 worktree 里改：数据集与删查表、评估客户端与清单、GroundSG 适配、PonderPounce 接入、Astra 接入、启动脚本与转码、对比与报告。前两块都要动步数查表，单独合第一块会让日常测试变红，所以两块各自在 worktree 里写完、审完，然后连着合入、合完两块再跑一次日常门禁并推送；中间三块并行，最后合启动脚本和报告。其余每次合并前由主会话复跑该块测试并派一个只读审查，合并后跑日常门禁再推送。子模块、新环境的依赖声明、契约总表、两份 README 由主会话自己做。长任务（本机预检、本机两档、GL 各席的链）的启动交给运行型子代理：每个只负责把一条写死的命令起起来、确认起跑成功、交回会话名和日志路径；盯盘、预算、Astra 的每一局、占位 job 和清理都留在主会话。

## 七、已由用户定下、执行方自行处理的事

- 占位 job 的规格与数量：单卡席位 4 CPU、64 GB；Astra 两卡 6 CPU、64 GB。
- PonderPounce 单张 A40 放不下：改成单独的两卡 job，单卡席位相应减少；两卡仍不行则停掉这条线并记入决策项。
- `flash-attn` 编译失败：不改第三方代码去换实现；QwenVL 与 Astra 两条线停下并记入决策项，其余照常。
- PonderPounce 的加速内核：按预检耗时决定装不装，两侧一致。
- PaliGemma 分词器的访问许可：2026-10-04 已实测可读。

**2026-10-04 审计后用户放行的 12 项**（原话第 23、26 条）

| # | 事项 | 定下的做法 |
|---|---|---|
| 1 | 第一块单独合入会让日常测试变红 | 第一、二块连着合入，合完两块再跑门禁 |
| 2 | 已提交的 9 个占位 job | 保留排队；开工前卡先到则空转，不自动开工 |
| 3 | PonderPounce 本机驱动不够 | 本机单建环境：torch 版本不变，只换成 CUDA 12 构建，原侧新侧都用它；GL 用官方环境，不换驱动、不换 torch |
| 4 | Astra 原侧要用它自带的那份官方环境代码 | 允许检出，只供 Astra 原侧；起跑前与本仓库 `src/robomme` 逐文件比对，差异为 0 才跑 |
| 5 | Qwen3.5-9B 与 PaliGemma 的分词器要下载 | 放行，钉死 40 位版本号 |
| 6 | Astra 的费用上限 | 只设金额：预检与正式运行合计 30 美元 |
| 7 | 预检修复后的重跑 | 每条路线最多另跑 2 局，用完停该线 |
| 8 | 第一档重跑预算不够两个集合同时用 | 保持 20 局，V9 优先，排不上的标「未定性」 |
| 9 | 48 小时到期 | 允许续交，同时在用不超过 10 张卡，只跑未完成的局；到期打断不扣故障重试额度，另设每模型 100 局的续跑上限 |
| 10 | Astra 两卡 job 跑完后 | 借给其他模型跑第三档，不与 Astra 同时运行 |
| 11 | 成绩怎么标 | 按第五节的表 |
| 12 | 第二、三档顺序 | 逐席衔接 |

## 八、还需要用户处理的事

1. **说「开工」。** 只有这两个字（或同样无歧义的指令）算数。
2. **密钥已出现在对话里**：跑完后可在 OpenAI 后台作废重发。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1 不改 `src/robomme/**`（P2），不改 `scripts/dataset_replay.py`、`evaluation.py`、`run_example.py`（P1），`scripts/` 顶层不新增文件。
- R2 不改任何第三方源码与既有 gitlink；新增第三方只以「子模块 + 锁定 gitlink」引入。`third_party/mme-vla/third_party/robomme_benchmark` 保持空目录。
- R3 `hard_specs.EXEC_CAP`、已封存规格、`packaged_specs.sha256`、`XHARD0_IN_TEST_HARD` 开关、`xhard0_prefix()` 一律不动——它们属于生成侧，第一档对拍靠它们保持字节不变（xhard0 生成遍仍以 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` 运行）。
- R4 Astra 的每一局都在已批额度内：本机 ≤6、GL 第二档 32、V9 连通 1。额度外不发起任何会调用 GPT 的运行；Astra 的基础设施重试额度为 0（指不重跑同一局；`api_client.py::_send` 自带的 429 请求级重试最多 9 次发送保留，逐次记入费用账）。预检与正式运行累计花费上限 30 美元（原话第 23 条，执行方按「合计一个上限」理解），机制见 1.5。
- R5 密钥只在 `~/.config/astra/openai.key`（本机，600）与 GL 登录节点同路径文件里，运行时以环境变量传入；不进仓库、日志、留档、命令行参数。
- R6 第一档 FAIL 不改参照、不改判据，也不停后续；第二档有差异不重跑挑结果，也不停后续；正常 fail／timeout 不重试。会让运行停下的只有：某条路线预检不过（只停该路线）、基础设施故障超出重试额度（只停该席位链，剩余分片由主会话重分给其他席位）、预算耗尽、Astra 的规划服务出错或花费到线（只停 Astra）。正文里凡写「报告用户」的分支，一律按「记入决策项、其余继续」执行，不停下等答复。
- R7 占位 job 同时在用 ≤10 张卡（续交的 job 与在跑的合计）；只 `scancel` 本轮清单里的 JobID；tmux 只按精确名清理。
- R8 现有主环境 `.venv` 与 `uv.lock` 不动；新依赖全部进独立环境。
- R9 开工只认用户明确、无歧义地说「开工」（正本第 2 条，`3fe9c80`）。此前只许只读核实与改本计划；不改代码、不下载、不提交或取消作业、不挂监听。卡先于开工令到手时不自动开工。
- R10 正本第 24 条「嵌套的第二份同名源码目录必须不存在或为空」的有限豁免（用户 2026-10-04 放行）：`third_party/Astra-on-RoboMME/third_party/robomme_benchmark`（`856bc3a`）允许初始化，只供 Astra 原侧 `run.sh` 使用。起跑前逐文件比对它的 `src/robomme` 与本仓库 `src/robomme`，判定行 `ASTRA_NESTED_ROBOMME=PASS files=<n> diff=0`；不为 0 则 Astra 原侧不跑并记入决策项。`third_party/mme-vla/third_party/robomme_benchmark` 仍保持空目录。

## 一、逐文件改动清单

### 1.1 数据集 `test-hard0` 与删除步数查表（S1）

| 文件::锚点 | 现状 | 改成 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_specs.py::TIER_MAX_STEPS` 及其上方注释 | `{"xhard0":1300,"xhard1":1600,…}` | 删除 |
| 同文件模块级 `assert all(TIER_MAX_STEPS[tier]==EXEC_CAP …)` | 导入期断言 | 随表删除（不删则 import 即失败） |
| 同文件 `EXEC_CAP`、`XHARD0_IN_TEST_HARD`、`xhard0_prefix`、`XHARD0_EPISODES`、`XHARD0_PER_TASK` | 生成侧常量与开关 | 不动（R3） |
| `env_record_wrapper/__init__.py` | 再导出 `TIER_MAX_STEPS`、`TEST_HARD` | 去掉前者，新增导出 `TEST_HARD0` |
| `hard_builder.py::_ALLOWED_DATASETS` | `{"train","test","val",TEST_HARD}` | 加 `TEST_HARD0 = "test-hard0"` |
| `hard_builder.py::BenchmarkEnvBuilder.__init__` | 只有 `TEST_HARD` 分支 | 父类参数：`dataset in {TEST_HARD, TEST_HARD0}` → `"test"`；`override_metadata_path` 的拒绝扩到 `TEST_HARD0`；新分支 `self._episode_map = dict(enumerate(_xhard0_entries(env_id, self.metadata_index)))`、`self.metadata_index = {}`，不读规格根；`TEST_HARD0` 下传入 `specs_root` 抛 `ValueError`；保留 `env_id in ALL_TASKS` 校验 |
| `hard_builder.py::_xhard0_entries`、`resolve_identity`、`_hard_env_kwargs`、`make_env_for_episode` | 对 xhard0 条目已可用 | 不改逻辑，只更新 docstring |
| `hard_builder.py::_test_hard_entries(env_id, xhard0, root)` | 签名被植入插件 M10 依赖 | 签名不动 |
| `scripts/evaluation_hard.py` | `dataset="test-hard", max_steps=1600` | **不改**（`tests/static/test_entry_scripts.py` 钉死它与官方入口只差三处）；xhard0 的用法写进 README：把这两个实参改成 `"test-hard0"`、`1300` |
| `scripts/parity/hard_regression.py::cmd_reset_replay`、合作者入口 `cmd_eval_smoke`、`_env_digest_one` | 三处都用 `dataset="test-hard"` 混跑 xhard0 与新档，靠逐局 `TIER_MAX_STEPS[tier]` 给上限 | **逐局参数保留**（`make_env_for_episode(max_steps=…)` 的逐局覆盖是 builder 既有接口，不传就退回 builder 的单一值，混档下会把 V9 局变成 1300 或把 xhard0 局变成 1600）。改为模块内函数 `_cap_for(tier)`：`XHARD0_STEP_CAP if tier == "xhard0" else hs.EXEC_CAP`；三处调用、`cmd_eval_smoke` 输出行里的 `max_steps=`、三处 `TIER_MAX_STEPS` 的 import 一并改掉；docstring 同步。这是对拍工具内部按档取值，不属评估链路的查表 |
| 同文件 `_step_headroom_v8` | `x0cap = hs.TIER_MAX_STEPS["xhard0"]` | 模块常量 `XHARD0_STEP_CAP = 1300`（与上一行共用） |
| `scripts/injection-dev/site/subgoal_lengths.py::tier_caps` | 读 `TIER_MAX_STEPS["xhard0"]` | 本地常量 1300 |
| `tests/sim/test_reset_matrix.py::test_reset_cell` | `max_steps=hard_specs.TIER_MAX_STEPS[tier]` | `1300 if tier == XHARD0 else 1600` |
| `tests/contract/test_constants.py::test_tier_max_steps_new_tiers_1600_xhard0_unpinned`、`NEW_TIER_MAX_STEPS` | 断言查表 | 删除；`EXEC_CAP` 断言保留 |
| `tests/contract/test_builder_800.py::test_rejections` | 允许集合不含 `test-hard0` | 补接受与拒绝用例 |
| 新 `tests/contract/test_builder_hard0.py` | — | 16 任务逐局 `gym.make` 参数、`resolve_identity` 字段、局数 192、官方 hard 子集被破坏时报错、`specs_root` 被拒、规格读取函数打桩为「调用即失败」 |
| `tests/pipeline/site/test_site_catalog.py` | 期望值读表 | 常量 1300 |
| `tests/contract/mutants.json::M08`、`tests/mutation/plugins/mut_inproc.py`（M08 分支与预校验里的 `"xhard1" in hs.TIER_MAX_STEPS`） | 植入查表 | 删除 M08 及其预校验，连同 `SUPPORTED` 元组里的 `"M08"` |
| `tests/contract/contracts.delta.json` | `C03-CONSTANTS`、`C03-TIER-MAX-STEPS-XHARD0` 引用查表与 M08 | 改 symbol／oracle 文字与 mutants 列表，删已失效条目，新增 `test-hard0` 契约条目 |
| `tests/static/contracts.delta.json` 的 `C18-EVAL-HARD-MAX-STEPS` | 引用查表 | 归 S1 改文字（`tests/static/` 下只动这一条） |
| `tests/contract/test_constants.py` 的 docstring 与 Q16 note | 提到查表 | 同步文字 |

S1 合入后、S2 合入前，`scripts/eval-official/{env_client,eval_manifest}.py` 与 `tests/pipeline/eval/test_eval_manifest.py` 仍在读 `TIER_MAX_STEPS`，总表 `tests/contract/benchmark_contracts.json` 也还登记着被删的测试，日常门禁必红。处置见第二节「合并顺序」：S1、S2 连着合入，中间不跑全量门禁、不推送。

### 1.2 评估客户端、清单、报告（S2）

**`scripts/eval-official/env_client.py`**

| 锚点 | 改成 |
|---|---|
| `MAX_STEPS`、`tier_max_steps()`、`SeatRunner.tier_max` | 删除 |
| `build_parser` 的 `--max-steps` | 无默认值、必填 |
| 新参数 `--dataset {test-hard,test-hard0}`（必填）、`--strict-cap`（开关）、`--mme-variant {ground-sg-oracle,ground-sg-qwenvl}`、`--qwenvl-groundsg-adapter`、`--trace-root` | 见下 |
| `--policy` 的 `choices` | `["mme","smvla","mmesg","pp"]`；模块仍按 `load_sibling(f"{policy}_client")` 加载 |
| `EnvSession.__init__`／`EnvSession.builder` | 新增 `dataset` 形参，替换写死的 `"test-hard"` |
| `EnvSession.build` | `make_env_for_episode(self.builder_episode)`，不再逐局传步数 |
| `SeatRunner.builder_for` | 缓存键 `(task, dataset)`；`BenchmarkEnvBuilder(env_id=task, dataset=args.dataset, action_space="joint_angle", max_steps=args.max_steps)` |
| `validate_v8_identity`、`check_identity` | 去掉 `tier_max` 形参与 `effective_max_steps` 校验；身份模式由 `--dataset` 决定：`test-hard` 沿用现有 V8 严格校验（`spec_sha256` 为 64 位串）；`test-hard0` 要求 `tier=="xhard0"`、`candidate is None`、`spec_sha256 is None`、`source_episode` 为整数且与 builder 解析结果相等 |
| `V8_IDENTITY_KEYS` | 去掉 `effective_max_steps`，与 `eval_manifest.SHARD_ROW_KEYS` 同步 |
| `SeatRunner.run_one` | `eff = args.max_steps`；`EnvSession(max_steps=eff, step_cap=eff if args.strict_cap else None)`；`conn_info` 增加 `dataset`、`mme_variant`、`qwenvl_groundSG_adapter_path`、`trace_dir`、`policy_context`（仅进程内对象，不进 JSON） |
| `SeatRunner.base_record` 与结果行 | 保留键 `max_steps`、`effective_max_steps`（下游站点在读），值都取 `args.max_steps`；新增 `dataset`、`policy_variant`、`strict_cap` |
| `--v8` 开关与 `self.v8` | 删除；原先受它控制的行为在两个数据集下一律启用：结果行必写 `exec_steps`、`cap_hit`、`demo_frames`、`reset_calls`，录像目录用 `<key>.a<attempt>`，`policy_kwargs` 与 `_on_wall_timeout` 照 v8 分支。`step_cap` 只由 `--strict-cap` 决定。`run_seat.sh`、`run_eval_gl.sh`、`seat_fake_engine.py`、`gate_set.py` 注释里的 `--v8` 同步去掉（前两个归 S6）。加单测：`test-hard0` 结果行这四个字段齐全 |
| 账本（`--ledger`、`--reset-budget`、`--infra-retry-budget`） | 与身份模式、`--strict-cap` 解耦，两个数据集都启用。账本按席位各一份，**额度按模型共享**：主会话把每模型的重试额度（10）与续跑额度（100）切给各席，各席 `--infra-retry-budget` 之和等于模型额度，不是每席各 10。`attempt_end` 已写、`accept` 未写时崩溃的窗口：恢复路径对「最后一次 `attempt_end` 是最终结局但无 `accept`」的身份补写 `accept`，加单测。席位收尾与链的衔接读回真实报告（`eval_report.py` 的缺失数），不只看退出码：重试耗尽或身份缺失时退出码非 0 |
| `StepCapReached`／`cap_hit` | 机制不变，只在 `--strict-cap` 时生效 |

启动约定：`test-hard` → `--max-steps 1600 --strict-cap`；`test-hard0` → `--max-steps 1300`，不带 `--strict-cap`。

**`scripts/eval-official/eval_manifest.py`**

- 新增 `--mode {v9-new,v9-full,hard0}`，默认 `v9-new`（现有行为不变）。
- `v9-full`：`--identities` + `--delivery`，不要求 `--exclude-evaluated`，产出 800 行；判定行 `EVAL_SHARDS=PASS mode=v9-full total=800 cells=43 missing=0 extra=0 duplicate=0 xhard0=0`。
- `hard0`：直接由 `BenchmarkEnvBuilder(task, dataset="test-hard0")` 枚举，不读交付清单；`--per-task N`（默认 12）取每任务前 N 局；判定行 `EVAL_SHARDS=PASS mode=hard0 total=<16×N> xhard0=<16×N>`。行键与 `SHARD_ROW_KEYS` 相同，`spec_sha256=None`、`candidate=None`、`key=<task>_xhard0_<seed>`。
- `join_delivery` 不再写 `effective_max_steps`；`check_exec` 删去对应项，`xhard0==0` 的要求只在 V9 两种模式下保留。
- `--pair-shards`：`hard0` 模式下同一身份的原侧与新侧分到同一分片，文件 `shard-NN.json` 两侧共用。

**`scripts/eval-official/eval_report.py`**

- 新增 `--dataset`；`test-hard0` 时身份必备字段不含 `spec_sha256`，不做 `exec_over_cap` 判定（官方循环允许第 1301 步）。
- `--policies` 接受任意 `<policy>[:<variant>]` 列表；`--expect-total` 由调用方给 800 或 192。
- 判定行前缀参数化：`EVAL_COVERAGE=PASS dataset=… policy=… expected=… missing=0 extra=0 duplicate=0 conflicting_terminal=0 error_final=0`、`EVAL_VIDEOS=PASS … decode_fail=0`。

**测试**：`tests/pipeline/eval/` 下 `test_identity_contract.py`、`test_eval_manifest.py`、`test_eval_report.py`、`test_env_session.py`、`test_seat_runner_e2e.py`、`eval_fakes.py`（`tier_cap` 改常量、`real_builder` 加 `dataset`）同步；期望值一律手写 1300／1600，不读被测代码；同目录 `contracts.delta.json`、`mutants.json` 同步。

### 1.3 GroundSG 两组（S3）

**官方行为（已核实，`third_party/mme-vla/examples/robomme/`）**

- `eval.py::EpisodeEvaluator.eval_each_episode(env_runner, subgoal_predictor, video_save_dir)`：每局新建 `MMEVLAWebsocketClientPolicy(host, port)`；先 `env_runner.step(action)`、`count += 1`，再判 `count > max_steps` 记 `timeout`——`max_steps=1300` 时真实执行第 1301 步，且该步终态被覆盖为超时。
- `env_runner.py::EnvRunner.__init__(env_id, video_save_dir, max_steps=1300)`：官方 builder、`dataset="test"`、`action_space="joint_angle"`；Oracle 文本取自 `self.info["grounded_subgoal_online"]`，`info` 每步更新。
- `subgoal_predictor.py::build_subgoal_predictor` 优先级 gemini > qwenvl > memer > oracle，多开时静默取高优先级；`QwenVLSubgoalPredictor` 构造即加载模型，临时目录 `<save_dir>/<env_name>/ep<episode_id>`，`end_episode` 时 `rmtree`，日志 `ep<id>_QwenVL_log.jsonl` 在其父层保留。
- `subgoal_prediction/qwenvl/api.py::Qwen3VLModel`：`PtEngine('Qwen/Qwen3-VL-4B-Instruct', adapters=[adapter_path], attn_impl='flash_attention_2')`，`RequestConfig(max_tokens=128, temperature=0)`，没有 seed。
- 官方命令（`scripts/eval.sh`）：server `--seed=7 --port=$PORT policy:checkpoint --policy.dir=…/symbolic-grounded-subgoal/79999 --policy.config=mme_vla_suite`；配置由 checkpoint 父目录的 `history_config.txt`（内容 `symbolic-grounded-subgoal.yaml`）选定；客户端 `--args.use-oracle` 或 `--args.use-qwenvl`，加 `--args.subgoal-type=grounded_subgoal`。

**新文件**

| 文件 | 内容 |
|---|---|
| `scripts/eval-official/official_defs.py` | `extract_defs(path, names, extra)`：用 `ast` 从官方源文件取顶层函数、类、单目标赋值的原文并执行，返回命名空间并记 `__source_sha256__`（旧 `policy_replay.py` 已在 `27d209d5` 删除，按 `git show 27d209d5^:scripts/eval-official/policy_replay.py` 的同名函数重写）。另负责官方模块头部不会被摘走的三项环境设置：`IMAGE_MAX_TOKEN_NUM=256`、`VIDEO_MAX_TOKEN_NUM=64`、`FPS_MAX_FRAMES=10` |
| `scripts/eval-official/mmesg_client.py` | 新侧。`run_episode(session, identity, conn_info, recorder) -> dict`。从官方 `eval.py` 取 `EpisodeEvaluator`、`Args`，从 `subgoal_predictor.py` 只取所选变体需要的类（Oracle 变体不加载 Qwen；QwenVL 变体取 `QwenVLSubgoalPredictor`、`Qwen3VLModel`，不取 Gemini／MemER），构造前断言 `use_oracle` 与 `use_qwenvl` 恰有一个为真。runner 适配对象提供 `env_id`、`episode_id`（取 `<key>.a<attempt>`，两个数据集下都唯一；官方 Qwen 预测器用它拼临时目录 `<save_dir>/<env_name>/ep<episode_id>`，其父层的 `ep<id>_QwenVL_log.jsonl` 每局结束归档到 `trace_dir`）、`task_goal`（官方 `SubgoalPredictorBase.start_episode` 会读，在 `get_init_obs()` 里赋值）、`difficulty`、`info`、`get_init_obs()`、`step()`、`simple_subgoal_oracle`、`grounded_subgoal_oracle`，内部委托 `session.reset()`／`session.step()`，每步同步 `info`。预测器与 evaluator 由 `SeatRunner` 以 `policy_context` 持有、整席只建一次。Qwen 临时目录 `<trace_dir>/qwen-tmp/<dataset>/<key>.a<attempt>/`，与录像目录分开；`unknown` 或异常早退时由适配器清理本次登记的目录。官方 `unknown` 记为 `status="error"`、`error="success_flag=unknown"`，不中止整席。`StepCapReached` 在适配入口收住后原样交回 `run_one` 记 `timeout` |
| `scripts/eval-official/official_hard_runner.py` | 原侧。官方 `eval.py` 经 `subgoal_predictor.py` 无条件导入 gemini（`google.generativeai`）与 memer 模块，两个环境里都没装，所以原侧**不整模块 import**，与新侧一样用 `official_defs.extract_defs` 摘取 `EpisodeEvaluator`、`Args`、`EnvRunner` 与所选变体的预测器；解释器用客户端扩展环境。独立进程，`sys.path` 只加官方 `examples/robomme` 与本仓库 `src`；启动时断言 `robomme.__file__` 在仓库 `src/robomme/` 下、`"robomme_hard" not in sys.modules`。读 `hard0` 分片，对每个 `(task, source_episode)` 调官方 `EnvRunner(task, video_dir, max_steps=args.max_steps).make_env(source_episode)` 与 `EpisodeEvaluator.eval_each_episode`；在 MME 层以委托方式包住 `EnvRunner.get_init_obs`／`step` 与客户端 `infer` 记录轨迹，不碰 `src/robomme` 的任何方法 |

**官方录像**：`eval_each_episode` 自己会写一份带文字叠加的 mp4（文件名含自由文本 `task_goal`）；超时局执行 1301 步但只录 1300 帧，`unknown` 局在存视频前就返回、不出视频。交付视频与帧数公式见 1.7 的路线表。

**服务端随机数**：`openpi/policies/policy.py` 的 `self._rng` 每次 `infer` 都 `split`，每局开始不重置。两侧各起新服务、同 seed、同分片正序，只要调用序列相同就逐步一致；一旦某局分叉或发生重试，同一服务上后面的局都带随机数漂移。所以 `gate2_compare.py` 对 GroundSG 另出 `first_episode_identical=<n>/<服务启动次数>`，报告按第一部分第五节的读法解释。官方 `eval.sh` 把服务端与客户端放两张卡，本计划同卡共置，记为偏离。

**server**：两个变体共用 `symbolic-grounded-subgoal/79999`，`--seed=7`；`run_seat.sh` 的 `MME_YAML_EXPECT` 参数化（见 1.6）。QwenVL 变体与 VLA 同卡时 `XLA_PYTHON_CLIENT_MEM_FRACTION` 由预检定值（现为 0.75，需给 Qwen 4B 让出约 10 GB）。

**Qwen 运行约束**：`USE_HF=1`（ms-swift 默认走 ModelScope，本机该缓存残缺）、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`HF_HOME=<NFS hf-cache>`；`attn_impl='flash_attention_2'` 不改，客户端环境编译安装 `flash-attn==2.8.3`，编译失败报告用户，不改成 `sdpa`。

### 1.4 PonderPounce（S4）

**官方行为（已核实）**

- 模型以 vla-eval 的模型服务形式运行：`python -m ponderpounce.eval.robomme_server --args.checkpoint_path <目录> --port <端口>`；`GET /health` 返回 200 即权重已加载。
- 协议（`vla_eval.protocol`、`vla_eval.connection.Connection`，0.7.0 与 HEAD 一致）：msgpack 二进制帧；`HELLO` 握手 → 每局 `EPISODE_START`（无应答）→ 循环 `OBSERVATION`／`ACTION` → `EPISODE_END`。图像默认 PNG 无损。
- 驱动顺序（`vla_eval.runners.sync_runner.SyncEpisodeRunner.run_episode`）：`reset` → 首条观测（带 `video_history`、`task_description`）→ `for step in range(max_steps)`：发观测、收动作、`step`、已结束则 `break`（最后一帧不再发送）→ `EPISODE_END`。上限是恰好 `max_steps` 个动作。
- 观测键（`benchmark.py::RoboMMEBenchmark.make_obs`）：`images.agentview`、`images.wrist`、`states`（7 关节 + 1 夹爪，float32）、`task_description`；首条另带 `video_history = front_rgb_list[:-1]`。返回 `{"actions": float32 (1, D)}`，环境取前 8 维。
- 服务类 `PonderPounceRoboMMEServer` 的文档串为 "one GPU, one process"，整模型放一个设备，两张卡不能把模型切开；默认 `seed: int = 0`；启动时读 checkpoint 目录里的 `norm_stats.json`。
- 噪声种子 `crc32(f"{seed}:{sid}:{n}")`：`sid` 取 `EPISODE_START` 里的 `recording.sid`，缺省是每次启动随机的 uuid；`n` 是该 `sid` 在服务进程内的累计局数。官方默认下每次运行噪声都不同。
- 官方评估用 Docker 加 CPU 软件渲染；vla-eval 支持不走 Docker 的进程内运行，`RoboMMEBenchmark.configure_render("gpu")` 不改任何环境变量。
- 依赖：Python 3.11，`torch 2.14.0`（CUDA 13 构建）、`transformers 5.13.1`；可选内核 `flash-linear-attention`、`causal-conv1d`（后者只有源码包，需编译），不装则回退到慢数倍的纯 PyTorch 实现。启动时读 `Qwen/Qwen3.5-9B` 的配置与分词器、`google/paligemma-3b-pt-224` 的分词器，均未钉 revision，代码没有离线开关。

**本仓库的处理**

| 项目 | 做法 |
|---|---|
| 源码 | 子模块 `third_party/PonderPounce` @ `723df357…`，服务环境在该目录 `uv sync --frozen`（其 `uv.lock` 即可复现面） |
| 新 `scripts/eval-official/pp_client.py` | 新侧。`run_episode(session, identity, conn_info, recorder)`；用 `vla_eval.connection.Connection(url, timeout=300.0)`，顺序与 `SyncEpisodeRunner` 一致；观测由 `session` 的原始观测按 `make_obs` 同样规则打包；动作取 `actions[0][:8]`。`EPISODE_START` 带 `{"task": {"name","env_id","episode_idx"}, "recording": {"sid": <固定>, "eid": <固定>, "eval_id": "", "db_path": ""}}` |
| 新 `scripts/eval-official/pp_official_runner.py` | 原侧。独立进程，只导入官方 `robomme`（同 1.3 的断言）；`RoboMMEBenchmark.configure_render("gpu")` → `RoboMMEBenchmark(tasks=[task], action_space="joint_angle", max_steps=1300)` → 对分片里每个 `source_episode` 调 `SyncEpisodeRunner().run_episode(bench, {**t, "episode_idx": ep}, conn, max_steps=1300, recorder=<固定 sid 的记录器>)`；外围自己处理 `TimeoutError`、`ConnectionClosed`、`RuntimeError` 并 `reconnect`；`SyncEpisodeRunner` 在不带录制库时不出视频，本驱动在外围委托包住 `bench.reset`／`bench.step`，把每步的 `front_rgb_list[-1]` 与腕部画面交给 `trace_writer` 记哈希并写成压缩视频 |
| 固定 `sid` | xhard0：`<task>|<source_episode>|<seed>`；V9：`<task>|<tier>|<seed>`。两侧各起自己的服务进程，同一 `sid` 在一个进程内只用一次，保证 `n=0`；基础设施重试一律「先由席位脚本重启服务，再重发同一 `sid`」，驱动自己的 `reconnect` 只用于同一局内的断线、不重发 `EPISODE_START`。所有服务显式传 `--args.seed 0` 并记入 `launch.md` |
| 两卡的含义 | 服务本体单卡放得下、加上仿真渲染才不够：把仿真与客户端进程放到第二张卡。模型本体单卡就放不下：没有切分能力，按第一部分第七节停线 |
| 预检地点 | 本机驱动 `570.211.01` 低于 CUDA 13 构建要求的 580。本机按用户选定的做法 A：另建 `artifacts/sg-evaluation/pp-local-env/`（`UV_PROJECT_ENVIRONMENT` 指向它，不动 `third_party/PonderPounce/.venv` 与其 `uv.lock`），依赖照官方 `uv.lock` 解析，只把 torch 及其 CUDA 运行库换成**同一 torch 版本号**的 CUDA 12 构建；装好后打印 `torch.__version__`、`torch.version.cuda` 并跑 `torch.cuda.is_available()` 与一次空前向，判定行 `PP_LOCAL_ENV=PASS torch=<版本> cuda=12.x`。该 torch 版本没有 CUDA 12 构建、或空前向失败：本机 PonderPounce 停线并记入决策项（不升驱动、不改模型代码），GL 不受影响。本机的预检 4 局与第二档原侧、新侧都用这个环境；报告里标明「本机 PonderPounce 为 CUDA 12 构建」。GL 用官方环境，另在先拿到的单卡席位上跑 1 局 smoke 确认官方构建能加载（计入 GL smoke） |
| 步数 | xhard0 两侧都是恰好 1300 个动作（它的官方行为）；V9 `--max-steps 1600 --strict-cap` |
| 渲染 | 两侧都用 GPU 渲染，与本仓库其他模型一致；与论文的 CPU 渲染设置不同，报告里写明成绩不能直接对照论文数字 |
| 加速内核 | 预检时装与不装各测 1 局耗时（不装的那一局计入预检局数）；采用哪种由耗时决定，两侧与全部席位一致，并记入留档 |
| 离线 | 权重用本地目录；`HF_HOME` 指向 NFS 缓存，预先放入两套分词器文件后设 `HF_HUB_OFFLINE=1` |
| 驱动兼容 | GL 上次为 595.71，CUDA 13 构建能否加载由 GL 预检第一步 `torch.cuda.is_available()` 判定；不行则停这条线并记入决策项，不换驱动、不换 torch 构建 |

### 1.5 Astra（S5）

**官方行为（已核实，`examples/champ/`）**

- `run.sh <cases.json> <新目录>`：要求 `VLA_PYTHON`、`SIM_PYTHON`、`VLA_CHECKPOINT`、`MONITOR_BASE`、`MONITOR_ADAPTER`、`OPENAI_API_KEY`；`VLA_GPU` 与 `MONITOR_GPU` 相同即 `exit 2`；`PYTHONPATH` 被覆盖为指向它自己子模块的 `src`；VLA 以 `--seed=42` 启动且拿不到密钥；输出目录已存在即拒绝。
- `prepare_cases.py --dataset test --episodes 3` 产出 16 任务 × 第 3 局的清单；`validate_cases` 只接受 `test`／`val`、局号 0～49。
- `runner.py::episode(args, task, ep, builder, monitor, planner, client)` 是模块级函数，builder 由参数传入；只用到 `builder.make_env_for_episode`、`builder.resolve_episode`、环境的 `reset`／`step`／`close`、四个 `*_list` 观测键与 `info` 的 `task_goal`、`status`、`error_message`。循环 `while t < max_steps`，恰好 1300 步。
- 每次规划请求：`gpt-6-astra`、`reasoning.effort=medium`、`max_output_tokens=2048`、`store=False`、高细节图像；两次请求至少间隔 20 秒；只对 429 重试；出现规划服务错误会停掉整个分片。每局规划次数上限 24。
- 监视器：`PtEngine(base, adapters=[adapter], torch_dtype=bfloat16, attn_impl='flash_attention_2')`，`temperature=0`。
- 每局产物：`identity.json`、`decisions.jsonl`、`actions.npy`、`result.json`、`rollout.mp4`（imageio 压缩视频）、`monitor_inputs/`、`planner_calls/`。
- 它的 `src/`、`scripts/`、`packages/` 与本仓库 MME 子模块 `ecf086c3` 逐文件相同，动作模型就是 GroundSG 用的 `symbolic-grounded-subgoal/79999`。

**本仓库的处理**

| 项目 | 做法 |
|---|---|
| 源码 | 子模块 `third_party/Astra-on-RoboMME` @ `4c3fd6a8…`；它嵌套的 `third_party/robomme_benchmark`（`856bc3a`）只在这个子模块内初始化，供原侧使用（R10 的豁免与 `ASTRA_NESTED_ROBOMME` 比对） |
| `main()` 里新驱动必须复刻的行为 | 子模块入库后先读 `runner.py::main` 列出清单并写进 `launch.md`；已知至少三项：连续出错即停整个分片（规划类失败不计入连续数）、输出目录必须新建、每局前查 `STOP.json`。`ResponsesClient` 自带的两项不会因绕开 `main()` 丢失：`_send` 每次发送前查输出路径上名为 `group_0`／`group_1` 的目录里的 `STOP.json`；`api_started.json` 存在而无 `response.json` 时拒绝自动重发。所以新侧输出目录保留 `group_0/` 这一层 |
| 费用上限 | 累计花费 = 两侧全部 `planner_calls/*/response.json` 的 `usage` × 单价（含监视器之外的复审请求、429 重发成功后的那一次；单价开工后查 OpenAI 官方价目并记入 `launch.md`）。一个常驻的 `astra_cost_guard.py`（归 S5）每 10 秒汇总一次，写 `ASTRA_COST usd=<累计> calls=<n>`；累计加上「一次请求的最坏花费」（已见最大输入量 + 2048 输出）超过 30 美元时，在当前 `group_*/` 下写 `STOP.json`（Astra 自带的停机口），判定行 `ASTRA_COST=STOP usd=… cap=30`。本机预检与 GL 运行共用同一份累计（预检的账本拷到 GL）。到线后 Astra 剩余局不跑，记入决策项 |
| 出错处置 | 规划服务出错、花费到线、`api_started.json` 结果未知：停 Astra 当前侧及之后的全部局，另一侧已跑完的保留，不重跑。仿真或 VLA 服务故障：该局记 error，不重跑（重试额度 0），继续下一局；连续 3 局则停。正常 fail／timeout：继续。原侧停了，新侧仍按已批局数跑（反之亦然），除非原因是花费到线 |
| 原侧 | 原样运行它的 `run.sh`：`prepare_cases.py --dataset test --episodes 3` → `VLA_GPU=0 MONITOR_GPU=1 PORT=<端口> bash examples/champ/run.sh <cases> <新目录>` |
| 新 `scripts/eval-official/astra_hard_runner.py` | 新侧。`sys.path` 加 Astra 的 `examples/champ` 与本仓库 `src`；`import robomme_hard.robomme_env`；`builder = BenchmarkEnvBuilder(task, dataset=<test-hard0 或 test-hard>, action_space="joint_angle", gui_render=False, max_steps=<1300 或 1600>)`；构造 Astra 的 `Monitor`、`Planner`、`ResponsesClient` 与 websocket 客户端后直接调用 `runner.episode(...)`，不经过它的 `main()`（其中的 `metadata_index` 与 50 局断言对本仓库 builder 不成立）。输出目录结构与原侧相同 |
| 新 `scripts/eval-official/run_astra.sh` | 新侧启动器：环境变量与 VLA 启动命令逐项照抄 `run.sh`（含 `--seed=42`、`XLA_PYTHON_CLIENT_PREALLOCATE=false`、`USE_HF=1`、`HF_HUB_OFFLINE=1`、`IMAGE_MAX_TOKEN_NUM=128`、`env -u OPENAI_API_KEY` 启动 VLA），只把 `PYTHONPATH` 的环境源换成本仓库 `src`；另设 `NO_PROXY=127.0.0.1,localhost`；启动前打印 `robomme_hard.__file__` 与 `robomme.__file__` |
| 身份 | 第二档：16 任务各取官方 `test` 的 episode 编号 3（零基，`prepare_cases.py --episodes 3`），即 `test-hard0` 的本地局号 0；新驱动传给 `runner.episode` 的局号是 0，并断言 `builder.resolve_identity(0).source_episode == 3`；V9 连通：`VideoUnmask` 的 xhard1 第一局（规划次数少的任务） |
| 步数 | xhard0 两侧 1300；V9 连通局 1600 |
| 两卡 | 按官方要求一张卡给 VLA、一张给仿真与监视器，单独的两卡 job |
| 仿真版本 | 官方文档在仿真环境里把 SAPIEN 覆盖到 3.0.3；本计划两侧都用 3.0.2（官方环境锁文件与本仓库一致的版本），差异写进报告 |
| 密钥 | 启动行 `OPENAI_API_KEY="$(cat ~/.config/astra/openai.key)"`；GL 上从登录节点 tmux 启动，变量经 `srun` 传入计算节点 |
| 对比 | 规划来自在线模型，两侧不会逐步相同；只比成功率、每局子任务序列、规划与监视次数 |
| 停机 | Astra 自带「规划服务出错即停整个分片」保留；停下后剩余局不自动重跑，报告用户 |

### 1.6 启动脚本与转码（S6）

| 文件 | 改动 |
|---|---|
| `scripts/eval-official/run_seat.sh` | 新参数 `--dataset`、`--max-steps`、`--strict-cap`、`--mme-variant`、`--qwenvl-groundsg-adapter`、`--pp-ckpt`、`--trace-root`，在 `start_client` 处透传给 `env_client.py run`。策略号：`smvla=0`、`mme=1`、`mmesg=2`、`pp=3`（端口 `18000 + 100×席号 + 10×策略号`）。`start_server` 新增 `mmesg`（与 `mme` 同命令，`MME_YAML_EXPECT` 取 `symbolic-grounded-subgoal.yaml`）与 `pp`（`cd third_party/PonderPounce && setsid env … "$PP_PY" -m ponderpounce.eval.robomme_server --args.checkpoint_path "$PP_CKPT" --args.device cuda:0 --port $port`，就绪判定用 `/health`）。`BENCH_PY` 对 `mmesg`、`pp` 默认取客户端扩展环境。不传新参数时行为与现在相同 |
| `scripts/eval-official/run_eval_gl.sh` | 透传上述参数；`--policies` 接受 `mmesg`、`pp`；`COND` 改为由参数给出；每局录像在同步前就地转码：复用 `scripts/injection-dev/site/eval_transcode.py` 的参数（`libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -movflags +faststart`，30 fps），核对帧数一致后删除节点上的原始帧，把 mp4、`summary.json` 与该局的 `trace.jsonl` 发布到 NFS。NFS 上的输出键为 `<policy>[-<variant>]/<dataset>/<side>/<key>.a<attempt>/`（`side` 取 `orig`／`new`），两个 `mmesg` 变体、原侧与新侧互不覆盖。判定行 `SEAT_REC_SYNC=PASS … transcoded=<n> frame_mismatch=0` |
| 新 `scripts/eval-official/run_official_hard.sh` | 原侧席位启动器：起模型服务（同上命令）→ 跑 `official_hard_runner.py` 或 `pp_official_runner.py` → 转码与同步 → `trap` 清理；判定行 `OFFICIAL_SEAT_DONE seat=NN policy=… outcome=… rc=…`、`EXIT_CODE=` |
| 新 `scripts/eval-official/pair_seat.sh` | 第二档一席的串行链：同一分片先原侧后新侧，同一张卡，前一侧的服务完全退出、显存释放后再起后一侧 |
| `scripts/injection-dev/eval_video_mover.py` | 现只认 `V8_MEDIA = ("front.mkv", "wrist.mkv")`。新增 `--layout sgeval`：认上面的输出键与每局单个 mp4、`trace.jsonl`，两端 sha256 相同才删 NFS 源；sha256 不一致或本机盘剩余低于阈值时停止搬运、保留 NFS 源并打 `MOVER_STOP reason=…`。默认布局行为不变。测试 `tests/pipeline/eval/test_eval_video_mover.py` 补用例 |

三个新启动器（`run_official_hard.sh`、`pair_seat.sh`、`run_astra.sh`）的守卫：前两个 `source` `run_seat.sh` 里现成的 `port_busy`、服务进程 `kill -0` 存活检查、`NO_PROGRESS` 无进展检测与首局 600 秒放宽，不另写一套；`run_astra.sh` 只加端口探测与 `trap`，不加无进展看门狗（Astra 请求之间本来就有 20 秒间隔和长退避，保持官方行为）。`EVAL_WIRING` 的测试断言这些守卫在场。

### 1.7 轨迹记录、对比、报告、资源探针（S7）

| 文件 | 内容 |
|---|---|
| 新 `scripts/eval-official/trace_writer.py` | 每局一个 `trace.jsonl`：每步 `{step, front_sha256, wrist_sha256, state(float32×8 的 hex), action(float32×8 的 hex), subgoal, terminated, truncated, status}`，首行含演示帧数与各帧哈希。原侧与新侧驱动都调用它；哈希在画面进入编码器之前计算。为避免「假一致」另记：发给模型的每次请求（`reset`／`add_buffer`／`infer`，PonderPounce 为每个协议帧）的规范化字节 sha256、演示阶段的状态与文本、历史缓冲的边界步号、模型返回的完整动作块；状态与动作按原始 dtype 和 shape 记录（字段 `dtype`、`shape`、`sha256`），不先转 float32。`identical_trace` 的含义限于这些字段，报告里写明覆盖范围 |
| 新 `scripts/eval-official/gate2_compare.py` | 读两侧 `trace.jsonl` 与结果行，按 `(task, source_episode, seed)` 配对；输出逐身份表：是否同终态、首个分叉步、分叉类型（画面／状态／文本／动作／停止步）。判定行 `GATE2=INFO policy=… compared=192 same_terminal=<n> identical_trace=<n> first_diverge_{obs,state,text,action}=<n> missing=0`。两侧身份不齐为 `GATE2=INCOMPLETE`。Astra 模式只比终态与子任务序列 |
| 新 `scripts/eval-official/model_eval_report.py` | 汇总各模型、各数据集、各入口的覆盖与成功率（按任务、按档），并入第二档差异与预算账本；判定行 `MODEL_EVAL_REPORT=PASS sets=<n> …`、`EVAL_BUDGET=PASS attempts<=… resets<=…` |
| 新 `scripts/eval-official/cap_probe.py` | 预检用，不加载任何模型。对给定 `--dataset`、`--max-steps`、任务与局号建 builder（`--official` 时用官方 builder 与 `dataset="test"`），先打印 `builder.max_steps_without_demonstration`（应为 `max_steps + 2`），再按所选循环口径用「保持当前关节位置」的动作一直走到结束，报告实际执行步数与终态。口径：`--loop strict` 为 `EnvSession` 加 `step_cap`；`--loop mme` 为官方 `count > max_steps`；`--loop range` 为 `range(max_steps)`。判定行 `STEP_CAP=PASS dataset=… max_steps=… builder_cap=… loop=… exec_steps=… terminal_reason=…`，预期 `mme`：1301／`loop_count`（环境若先截断则如实报 `env_truncated` 与步数），`range`：1300／`loop_exit`，`strict`：1600／`strict_cap`。xhard0 只真跑一局 `mme` 循环；`range` 的结论取自这一局的前 1300 步（空动作确定、前缀相同），判定行标 `source=prefix`，不写成真实跑过两条循环；循环口径本身另由 CPU 夹具测试覆盖 |
| 新 `scripts/eval-official/video_check.py` | 对一个结果目录逐局检查：恰有一个 mp4、`ffprobe` 编码为 h264、完整解码无错、帧数符合下方路线表的公式、mp4 所在目录的输出键与结果行身份一致、节点与 NFS 上没有残留的原始帧。判定行 `VIDEO_SAVED=PASS route=… episodes=… missing=0 decode_fail=0 frame_mismatch=0 raw_left=0 bytes=…` |
| 新 `scripts/eval-official/resource_probe.py` | 预检用。单个常驻进程，每秒读一次给定 PID 的进程树 `/proc/<pid>/status` 里的 `VmRSS`、`VmHWM`，以及 `nvidia-smi --query-compute-apps=pid,used_memory --format=csv -i <指定卡>`；输出 `PREFLIGHT=PASS route=… rss_peak_gb=… vram_peak_mb=… episode_s=… cpu_cores_used=…` |

**视频路线表**（`video_check.py` 按它判；各路线的演示帧口径在预检第一局实测后填入 `launch.md`，填入后不再改）

| 路线 | 交付的 mp4 | 帧数公式 | 特殊情形 |
|---|---|---|---|
| 新侧（三个模型，两个数据集） | 本仓库录像器的原始帧就地转码 | 录像器实际写出的帧数（转码前后相等）；与 `demo_frames + exec_steps` 的关系预检实测后固定 | `NO RECORD` 阶段不出帧是录像器既有设计 |
| GroundSG 原侧 | 外围委托记录的画面转码；官方循环自己写的叠字 mp4 不交付、局末删除 | 演示帧 + 已执行步数 | 官方循环超时局执行 1301 步而它自己的录像只有 1300 帧，交付视频以外围记录为准、含第 1301 帧；`unknown` 局记 error，预期无官方视频，外围视频照存 |
| PonderPounce 原侧 | 外围包住 `bench.reset`／`bench.step` 记录的画面转码 | `video_history` 帧数 + 已执行步数 | — |
| Astra 两侧 | 它自己的 `rollout.mp4` | 按它的录制口径，预检实测 | `monitor_inputs/`、`planner_calls/` 里的原图只在运行中临时使用，局末删除，保留请求哈希、文本、顺序与响应 |

容量：预检测得每局字节数后，按「局数 × 每局字节」估总量写入 `launch.md`，并核对 NFS 与 `/data` 的剩余空间；估算值与剩余空间一并记入决策项，不停跑。

### 1.8 主会话自做

| 项目 | 理由 |
|---|---|
| 两个新子模块的 gitlink、`.gitmodules` | 第三方来源与 gitlink 归主会话 |
| 新 `scripts/eval-official/client-env/{pyproject.toml,uv.lock}` | 依赖声明归主会话。内容：本仓库（路径依赖，含 `eval-client` 组）+ `ms-swift==3.11.1`、`qwen-vl-utils==0.0.14`、`transformers==4.57.3`、`peft==0.18.1`、`imageio`、`imageio-ffmpeg`、`vla-eval==0.7.0`；`flash-attn==2.8.3` 在环境建好后带 `--no-build-isolation` 编译安装并记录构建信息。供 QwenVL 预测器、PonderPounce 客户端、Astra 的仿真与监视器共用。解析冲突（如 `websockets` 版本）时拆成两个环境 |
| `tests/contract/benchmark_contracts.json` 合并、新文件登记 | 公共件。**每次合并前**主会话把该块的 `contracts.delta.json` 并入总表，并在总表 `files`／`nodeids` 登记该块新增的 `scripts/eval-official/*` 与测试文件（`tests/static/test_inventory.py` 要求 `scripts/` 下每个跟踪文件都已分类）；这次总表改动与该块的合并提交相邻提交，合并后审查跑 `tests/static` |
| `trace_writer.py` 的接口桩 | S3～S5 都要调用它，而 S7 最后合。主会话在派 S3～S5 之前先提交一个只含函数签名与字段约定的桩（S7 之后填实现），S7 的可写集合含这个文件 |
| 派 S3～S5 之前的准备 | 两个新子模块入库、`client-env` 建好。worktree 里子模块目录为空，S3～S5 的测试用环境变量 `SGEVAL_THIRD_PARTY=<主检出>/third_party` 只读引用官方源码，并打印所读文件的 sha256；`vla_eval`、`swift`、OpenAI 客户端一律用替身。测试里禁止用 `importorskip`／`skip` 绕过缺依赖，缺了就失败 |
| 判定行由谁打印 | 分配表里每个判定行（`HARD0_INTERFACE`、`STEP_LOOKUP`、`DATASET_ROUTING`、`OFFICIAL_ADAPTER` 等）由该块新增的一个同名测试在通过时 `print`，主会话复跑验收时用 `-s` 取原文 |
| `scripts/README.md`、`src/robomme_hard/README.md`、`AGENTS.md` 中对 `evaluation_hard.py` 的过期描述、`docs/1002-pending-decisions.md` 的 B5 | 文档 |
| 资产拷贝与核对、留档、全部监听、预算账本、Astra 的每一局、占位 job 的提交与取消、tmux 清理 | 资源与预算归主会话 |
| 本机预检、本机两档、GL 各席链的**启动** | 交运行型子代理（见第二节末的运行型子任务表）；主会话收回句柄后自己挂监听 |

## 二、子代理分配表

`BASE` 在派发时记当前 HEAD。公共禁触：`src/robomme/**`、`third_party/**`、`uv.lock`、`pyproject.toml`、`.gitmodules`、`tests/_support/**`、`tests/conftest.py`、`tests/contract/benchmark_contracts.json`、`scripts/` 顶层、其他块的文件。验收环境：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <路径> -q`，先打印 `robomme_hard.__file__` 确认指向 worktree。全部是 CPU 测试，不占 GPU、端口随机、不起 tmux。

| 编号 | 目标 | 可写文件集合 | 依赖 | 合并顺序 | 验收与判定行 |
|---|---|---|---|---|---|
| S1 | 数据集与删查表 | 1.1 表内全部文件 | 无 | 1 | `tests/contract tests/unit/hard tests/pipeline/site tests/pipeline/parity -m 'not slow'`；`HARD0_INTERFACE=PASS tasks=16 per_task=12 total=192 specs_reads=0`、`STEP_LOOKUP=PASS tier_max_steps_refs=0` |
| S2 | 评估客户端、清单、报告 | `scripts/eval-official/{env_client,eval_manifest,eval_report}.py`；`tests/pipeline/eval/` 下 1.2 列出的测试与 `eval_fakes.py`、`contracts.delta.json`、`mutants.json` | S1 | 2 | `tests/pipeline/eval -m 'not slow'`；`DATASET_ROUTING=PASS crossed=0 default_changed=0`、`EVAL_SHARDS=PASS mode=hard0 total=192` |
| S3 | GroundSG | 新 `official_defs.py`、`mmesg_client.py`、`official_hard_runner.py`；新 `tests/pipeline/evalx/groundsg/` | S2 的 `conn_info` 与 `run_episode` 约定 | 3（与 S4、S5 无先后） | 固定输入下新适配与官方循环的请求、动作、终态一致（Qwen 引擎用不加载权重的替身）；`OFFICIAL_ADAPTER=PASS variants=2 payload_diff=0 exec_diff=0 terminal_diff=0`、`OFFICIAL_HARD_SOURCE=PASS robomme_hard_imported=0` |
| S4 | PonderPounce | 新 `pp_client.py`、`pp_official_runner.py`；新 `tests/pipeline/evalx/pp/` | S2 | 3 | 假服务下新客户端与 `SyncEpisodeRunner` 的消息序列逐帧相同；`PP_PROTOCOL=PASS frames_diff=0 order_diff=0` |
| S5 | Astra | 新 `astra_hard_runner.py`、`run_astra.sh`、`astra_cost_guard.py`；新 `tests/pipeline/evalx/astra/` | S1 | 3 | 规划、监视、VLA 全部替身，零外联；`ASTRA_WIRING=PASS api_calls=0 builder_dataset_ok=1`；另测：规划替身第 k 局报错后不再发请求、连续 3 局基础设施错误即停、花费替身到线后写出 `STOP.json`，`ASTRA_STOP_RULES=PASS cases=3` |
| S6 | 启动脚本与转码 | `run_seat.sh`、`run_eval_gl.sh`、新 `run_official_hard.sh`、`pair_seat.sh`；`scripts/injection-dev/eval_video_mover.py`；`tests/pipeline/eval/test_seat_scripts.py`、`seat_fake_engine.py`、`test_eval_video_mover.py` | S2～S5 的参数名 | 4 | `bash -n` 四个脚本；`-m slow tests/pipeline/eval/test_seat_scripts.py`；`EVAL_WIRING=PASS routes=<n> dataset_mismatch=0 variant_mismatch=0` |
| S7 | 轨迹、对比、报告、探针 | 新 `trace_writer.py`、`gate2_compare.py`、`model_eval_report.py`、`resource_probe.py`、`cap_probe.py`、`video_check.py`；新 `tests/pipeline/evalx/report/` | S3～S5 的轨迹字段 | 5 | 夹具覆盖缺身份、重复、动作改 1 bit、画面哈希改变；`GATE2_SELFTEST=PASS` |

**S1 与 S2 的合并**（用户放行第 1 项）：两块照常各自在 worktree 里写、各自过合并前审查。S1 审查通过后先 `--no-ff` 合入本地工作分支，只跑 S1 的验收路径，**不推送**；随后从这个 HEAD 派 S2（worktree 基于当前 HEAD，S2 看得到 S1 的改动）。S2 审查通过后 `--no-ff` 合入，然后才跑日常门禁并出一条覆盖两次合并的 `POST_MERGE_REVIEW`，PASS 后一次推送。S1 合入到 S2 合入之间本地分支处于「日常门禁已知为红」的状态，期间不推送、不做别的提交（总表同步提交除外）；这是正本第 11 条「立即 push」在本计划内的一次性例外。S2 的可写集合不含 `tests/pipeline/eval/test_seat_scripts.py`、`seat_fake_engine.py`、`test_eval_video_mover.py`（归 S6）。

共享文件裁决：`env_client.py` 只归 S2；两个现有启动器只归 S6；`trace_writer.py` 归 S7，S3～S5 先按 1.7 的字段约定写调用，S7 合入后由主会话核对；各块新增的契约条目写在自己目录的 `contracts.delta.json`，由主会话并入总表。每块合并按 `CLAUDE.md`「计划执行模式」做合并前审查与合并后审查。

**运行型子任务**（`CLAUDE.md`「运行型子代理」；`model: "opus"`，不加 worktree 隔离；只启动、验证起跑、交回句柄；不改文件、不提交或取消作业、不清理 tmux）

| 编号 | 启动什么（命令原文在开工后由主会话按第四、五节填入派发提示，子代理不得改参数） | 位置 | 会话名／资源 | 起跑成功的判据 | 交回 |
|---|---|---|---|---|---|
| R1 | 本机预检的非 Astra 路线（每张卡一条串行脚本） | 本机主检出 | tmux `sgev-local-pre-<卡号>`；本机两张卡 | 第一条路线的 `PREFLIGHT=` 行出现，或 15 分钟内无报错且进程存活 | 会话名、日志路径、首批判定行 |
| R2 | 本机第一档（旧码、新码两遍生成） | 本机主检出 | tmux `sgev-local-g1`；一张卡 | 旧码遍第一局结果行出现 | 同上 |
| R3 | 本机第二档（每张卡一条 `pair_seat.sh` 链） | 本机主检出 | tmux `sgev-local-g2-<卡号>` | 该链 1 局 smoke 的结果行与 `VIDEO_SAVED=PASS` | 同上 |
| R4 | GL 某席的链（`seat_chain.sh`，经登录节点 tmux 内 `srun --jobid=<该席 JobID>`） | GL 执行副本 | 登录节点 tmux `sgev-seat-<NN>`；该席的占位 job | `SEAT` 起跑横幅、`--dataset`／`--max-steps` 配对核对通过、1 局 smoke 结果行 | 会话名、JobID、节点、日志路径、首批判定行 |
| R5 | GL 第一档那一席的生成两遍 | GL 执行副本 | 登录节点 tmux `sgev-gate1` | `IMPORT_CHECK=PASS` 与第一局结果行 | 同上 |

- Astra 的任何运行（本机预检冒烟、GL 第二档、V9 连通）**不交子代理**，由主会话亲自启动：局数逐局审批、花费有上限。
- 同一决策点可并行派多个运行型子代理（如同时排到的多个席位各派一个 R4）；同一席、同一张本机卡只派一个。
- 子代理发现命令要改才能跑通：停下交回，由主会话改脚本并提交后重派；执行副本 HEAD 冻结期间的改动按第五节「通用」处理。
- 被「排到卡即唤醒」叫醒后，主会话按上表派 R4／R5，收回句柄后挂监听并登记 `launch.md`。

## 三、资产与环境

| 资产 | 本机来源 | NFS 落点（`N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu`） | 大小 |
|---|---|---|---|
| GroundSG 动作模型 | `/data/hongzefu/robomme_policy_learning-vqa-test/runs/ckpts/mme_vla_suite/symbolic-grounded-subgoal/{79999,history_config.txt}` | `$N/sg-eval/ckpt/mme/symbolic-grounded-subgoal/`（真实目录，不用符号链接） | 11 GB |
| QwenVL GroundSG 适配器 | 同上仓库 `runs/ckpts/vlm_subgoal_predictor/qwenvl/grounded_subgoal/checkpoint-1200` | `$N/sg-eval/ckpt/qwenvl-groundsg/checkpoint-1200` | 1.3 GB |
| Qwen3-VL-4B 底座 | `~/.cache/huggingface/hub/models--Qwen--Qwen3-VL-4B-Instruct`（revision `ebb281ec…`） | `$N/hf-cache/hub/` | 8.3 GB |
| openpi 分词器 | `artifacts/v8-evaluation/openpi-data/big_vision/paligemma_tokenizer.model`（sha256 `8986bb4f…`） | `$N/sg-eval/openpi-data/` | 小 |
| PonderPounce 权重 | 需下载 `worv-ai/ponderpounce-9b-robomme` @ `5691e056…`（已放行） | `$N/sg-eval/ckpt/pp/ponderpounce-9b-robomme/` | 27 GB |
| Qwen3.5-9B 与 PaliGemma 的分词器文件 | 需下载（用户 2026-10-04 放行；后者需访问许可）。下载时取当时的 40 位 commit 作为 `revision` 钉死并记入 `launch.md`，落盘后补写 `refs/main` | `$N/hf-cache/hub/` | 小 |
| Astra 监视器适配器 | 需下载 `bingaochen/Astra-on-RoboMME-Monitor` @ `18ac2831…`，`sha256sum -c SHA256SUMS` | `$N/sg-eval/ckpt/astra-monitor/` | 小 |

- 拷贝只用 `rsync -a`，逐文件 sha256 写入 `artifacts/sg-evaluation/<run>/inputs/assets.sha256`，两端比对；判定行 `ASSETS=PASS files=<n> mismatch=0`。资产表里所有 `revision` 在 `launch.md` 写全 40 位。下载来的资产另核发布源的文件清单：PonderPounce 权重目录必须含 `norm_stats.json` 等发布源列出的全部文件（缺文件时服务可能照样通过 `/health`），Astra 监视器按 `SHA256SUMS`。`ASSETS=PASS` 只保证两端字节相同，不保证数值逐位可对拍。
- 环境：主环境 `.venv`（不动）；`third_party/mme-vla/.venv`（GroundSG 与 Astra 的 VLA 服务）；`scripts/eval-official/client-env`（客户端扩展）；`third_party/PonderPounce/.venv`（PonderPounce 服务）。GL 侧解释器用 NFS 上 uv 管理的 3.11.14，`UV_LINK_MODE=copy`，`uv sync` 不中途打断。
- GL 执行副本：新建 `$N/robomme_benchmark-sgeval`（`git clone --no-hardlinks` 自本机，检出本轮冻结提交，`git -c protocol.file.allow=always submodule update --init`）；席位脚本开头核 HEAD 与工作区干净。

## 四、本机预检

| 路线 | 局 | 说明 |
|---|---|---|
| 生成 smoke | V9 `PickXtimes` xhard1 seed 16100000、xhard0 `PickXtimes` seed 510300，各 1 局 | 与正式遍相同的 `--workers 4` 命令形态（每次只有 1 个身份） |
| GroundSG + Oracle | 原侧 xhard0 1 局、新侧 xhard0 1 局、新侧 V9 1 局 | 3 局 |
| GroundSG + QwenVL | 同上 | 3 局 |
| PonderPounce | 同上，另加「不装加速内核」1 局 | 4 局；本机用 `pp-local-env`（CUDA 12 构建），`PP_LOCAL_ENV` 不过则本机停线 |
| Astra | 原侧 1 局、新侧 1 局；失败可追加，合计 ≤6 局 | 已批；本机只做这一项冒烟，花费计入 30 美元 |
| 修复后重跑 | 每条非 Astra 路线最多另跑 2 局 | 用完仍不过即停该路线、记入决策项，其余照常 |
| 步数到顶 | `cap_probe.py`：`test-hard0` 1300 一局、`test-hard` 1600 一局 | 2 局，不加载模型 |

- 任务选 `VideoUnmask`（Astra 同）；V9 取 xhard1。本机两张卡，非 Astra 的路线一次并行两条。
- 每条路线由 `resource_probe.py` 采样，记录服务进程、客户端进程各自与合计的内存峰值、显存峰值、单局耗时。
- 判读：内存峰值 × 1.25 与已申请的 64 GB 比较，超出的模型另交更大的 job；显存峰值超过 44 GB 视为单张 A40 放不下，该模型改用两卡 job。
- **步数上限核对**（每条路线都做）：从日志与结果行取四处数值并要求相等——启动命令的 `--max-steps`、builder 的 `max_steps_without_demonstration - 2`、发给模型侧的上限（GroundSG 官方 `Args.max_steps`、PonderPounce 驱动循环的 `max_steps`、Astra 的 `--max-steps`）、结果行的 `max_steps`。xhard0 的路线必须全是 1300，V9 的路线必须全是 1600，且 V9 路线 `strict_cap=true`、xhard0 路线 `strict_cap=false`。判定行 `STEP_CAP_WIRING=PASS route=… launch=… builder=… policy=… recorded=…`。
- **步数到顶实测**：`cap_probe.py --dataset test-hard0 --max-steps 1300 --loop mme` 预期执行 1301 步后记超时（GroundSG 官方循环的行为）；`--loop range` 预期恰好 1300 步（PonderPounce、Astra 的行为）；`cap_probe.py --dataset test-hard --max-steps 1600 --loop strict` 预期恰好 1600 步、第 1601 次不进环境。xhard0 只真跑一局：`range` 口径取这一局的前 1300 步（判定行标 `source=prefix`），不多跑。实测与预期不符：修复后在「修复后重跑」额度内重测，仍不符则把实测值记入决策项，各路线照常上集群。
- **视频核对**（每条路线都做，含三个模型的原侧与 Astra）：预检每局结束后跑 `video_check.py`，`VIDEO_SAVED=PASS` 才算该路线通过（不通过走「修复后重跑」）；同时记录每局视频字节数，用来复核总量估算。
- 本机起跑前先看两张卡上有没有别人的进程（`nvidia-smi --query-compute-apps` 查一次）；有则只用空闲的那张，不动别人的进程。
- 预检结束输出 `PREFLIGHT_SUMMARY=PASS|PARTIAL routes=<n> failed=<k> stopped_routes=<名单> step_cap_ok=… video_ok=…`，并给出席位规格与分配表、按实测单局耗时算出的总席位时长估算。`PARTIAL` 不拦通过的路线。

**本机第一档与第二档**（预检后无条件做，先第一档；全程不阻塞）

1. 第一档（粗信号）：旧代码取开工前的 `BASE`（`git worktree add --detach artifacts/sg-evaluation/<run>/old-wt <BASE>`，借主 `.venv`、`PYTHONPATH=<old-wt>/src`，起跑打印 `robomme_hard.__file__`），新代码取接线全部合入后的 HEAD。两侧各跑一遍 `hard_parity.py generate`（V9 `--side H2 --tier v9` 129 局、xhard0 `--side H --tier xhard0` 48 局，`--workers 4`，同一张卡、先旧后新）。对比用逐局 h5 摘要直接互比，不调用 `noise_gate.py gen-regress check`（它的前提是 A40）。判定行 `LOCAL_GEN_DIFF=INFO set=… compared=<n> identical=<n> differ=<n>`；`differ>0` 只列清单，等 GL 第一档定性。跑完删 `old-wt`。
2. 第二档：`eval_manifest.py --mode hard0 --shards 2 --pair-shards`；两张卡各一条 `pair_seat.sh` 链，GroundSG-Oracle 与 GroundSG-QwenVL 各占一张；PonderPounce（`pp-local-env`）排在先空出的那张卡后面，原侧、新侧各 192 局；`PP_LOCAL_ENV` 不过则跳过并记入决策项。输出落 `artifacts/sg-evaluation/<run>/local/`，判定行 `GATE2=INFO site=local …`。Astra 不跑。
3. 本机长任务进 tmux（前缀 `sgev-local-`），各挂一个监听；本机这两档与 GL 的运行互不等待，结论都只进「本机结果」一节。

## 五、闸门与运行手册

**占位 job**（登记到 `$N/gl-hold-logs/hold-jobs-sgeval-<日期>.txt`）

```bash
# 单卡席位
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:1 --gpu_cmode=shared \
  --cpus-per-task=4 --mem=64G --time=48:00:00 --job-name=sgev-hold-<NN> --wrap='sleep infinity'
# Astra 专用两卡 job
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:2 --gpu_cmode=shared \
  --cpus-per-task=6 --mem=64G --time=48:00:00 --job-name=sgev-astra-hold --wrap='sleep infinity'
```

暂定分配：Astra 1 个两卡 job；其余 8 张卡为单卡席位，三个模型按「局数 × 单局耗时」比例分。PonderPounce 若单卡放不下，改为单独的两卡 job 并相应减少单卡席位。合计不超过 10 张卡。

**已提交的占位 job（2026-10-04 12:49，执行方误把第 21 条读成立即开工后提交；随后用户叫停；用户已定保留排队）**：单卡 `sgev-hold-00～07` = 63188711、63188712、63188713、63188714、63188715、63188716、63188719、63188720；两卡 `sgev-astra-hold` = 63188721；清单 `$N/gl-hold-logs/hold-jobs-sgeval-20261004.txt`。提交时全部排队。当时账户 20 张卡的配额已被组内其他成员占满：一名成员的 12 张卡是长作业、10 月 13 日之后才结束，另一名成员的 8 张卡在 10 月 4 日 23:13 至 10 月 5 日 05:17 之间陆续结束，另有成员的大量作业也在排队。因此近期最多只可能拿到 8 张卡，10 张卡的分配是上限而不是预期；拿到的席位先跑，单卡席位与 Astra 两卡 job 谁先拿到谁先开始。除这次提交外未做任何实施动作。2026-10-04 13:08 复查：9 个全部 `PENDING`，原因 `AssocGrpGRES`。48 小时自 job 开始运行起算；开工令之前卡先到则空转，不自动开工（R9）。

**排到卡即唤醒**（原话第 25 条；开工后才挂，开工前不挂）

- 机制：主会话用宿主的后台命令起一个轮询（不是 tmux，退出时宿主会自动唤醒会话）：每 120 秒经 ControlMaster 执行 `squeue -h -j <本轮 JobID 清单> -o '%i|%j|%T|%r|%S|%N'`；任一 job 不再是 `PENDING`、或行数与清单不符，就打印 `WATCH=CHANGED` 与当时的全表后退出。
- 失败也要叫醒：ssh 连续 5 次失败打印 `WATCH=SSH_FAIL` 后退出（多半是登录连接断了，需要用户重做 Okta 验证，此时发通知）。
- 续挂：宿主的后台命令最长 2 小时，到时会唤醒一次，主会话立刻续挂同一命令；每次被唤醒处理完也立刻续挂，直到全部席位都已开始运行。
- 被唤醒后做什么：记下该 job 的开始时间与到期时间；按当时进度往这张卡上派能跑的活——接线与预检已完成就起该席的链，未完成就先用它做 GL 侧准备（建环境、拷资产、PonderPounce 的 GL 预检），不让卡空着。
- 边界（如实写明）：这个轮询是会话的子进程，会话被关掉就没了，job 本身不受影响；它只在主会话存活时有效。创建成功以宿主返回的任务号为准，记入 `launch.md`；没有任务号就写「唤醒未建立」。除 `WATCH=SSH_FAIL` 与全部结束外不给用户推通知。

**到期与续交**（用户放行第 9 项）

- 每个 job 到期前 2 小时该席不再派新分片；在途的一局跑完即止。
- 未完成的身份由主会话重新分片：先分给还有余量的席位；不够时续交同规格的占位 job（同时在用的卡数含排队中的续交 job 不超过 10），登记进同一份 JobID 清单。
- 续跑只跑账本里没有终态的身份；被到期打断的在途局不扣基础设施重试额度，计入「到期续跑」额度（每模型 ≤100 局）。
- `CHAIN_STOP` 的席位：主会话把它剩余的分片按同样办法重分给其他席位。
- Astra 两卡 job 跑完 33 局后，改作两个单卡席位接第三档分片；与 Astra 不同时运行。PonderPounce 若需两卡：取消两个尚在排队的单卡 job、改交一个两卡 job，总卡数不变。

**第一档**（1 个单卡席位；沿用 `docs/validation/maintenance-regress-20261004/` 的做法）

1. 身份清单：`gate_set.py export --set {v9,xhard0} --kind generate`（129 行、48 行）。
2. 改后代码的执行副本借用 `$N/robomme_benchmark-noise/.venv`，`PYTHONPATH=<副本>/src`；前提是 `uv.lock` 与 `f8f76fba` 零差异，起跑打印 `IMPORT_CHECK=PASS`。
3. 每遍：`noise_run_gl.sh --pass <遍名> --kind gen --out-root <暂存> --attempts n --resets 3n --retries 0 -- hard_parity.py generate --side H2 --tier v9 --manifest … --identities … --specs-root … --workers 4 --gpu 0 --out /tmp/<遍名> --stage <暂存> --expect-ref scripts/configs/noise-ref-20261003.json`；xhard0 遍 `--side H --tier xhard0` 并设 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1`。
4. 判定：`noise_gate.py gen-regress check --ref … --set {v9,xhard0} --new … --out … --rerun-identities-out …`。判定行如实记录，不作为放行条件；`NEED_RERUN` 时在第三档全部跑完之后、释放席位之前，用空出的席位同节点先改后代码、再旧代码各跑一遍重跑清单，按四格定性，定性结果进决策项；单个集合翻转超过 10 局不做重跑，直接记 FAIL 进决策项。两个集合共用 20 局重跑预算（含陪跑局，新旧两侧都计）：先排 V9 的清单，剩余额度给 xhard0；排不进的身份标「未定性」，对应第一部分第五节的第二行标注。
5. 驱动与基线 `595.71.05` 不同：记入决策项，照常跑。
6. 第一档的证明边界：参照里登记为 `jitter` 的身份只作信息项、不参与判定；xhard0 遍走的是旧生成路线（`ROBOMME_HARD_XHARD0_IN_TEST_HARD=1`），不覆盖新增的 `test-hard0` 包装链。报告里照此写，不写成「新入口正确」。

**第二档**（GroundSG 两组与 PonderPounce）

1. `eval_manifest.py --mode hard0 --shards <席数> --pair-shards` 产出分片。
2. 每席 `pair_seat.sh`：原侧 `run_official_hard.sh` → 新侧 `run_eval_gl.sh --dataset test-hard0 --max-steps 1300`。
3. 每条路线先跑 1 局 smoke，再放到 192 局。
4. `gate2_compare.py` 出差异表；结果不影响第三档。

**第二档（Astra）**：两卡 job 内先原侧 16 局、后新侧 16 局；起跑前在计算节点上做一次不产生费用的模型查询确认代理可达；第一局即视为试跑，失败则停 Astra 并记入决策项，不自行重跑。`astra_cost_guard.py` 与运行同时起，累计含本机预检的花费。随后跑 V9 连通 1 局。

**席位队列**：每个单卡席位的串行链为「本席的第二档分片（`pair_seat.sh`）→ 本席的第三档分片」，由一个 `seat_chain.sh`（一次性脚本，归档到 `records/`）顺序调用。前一段因基础设施原因非 0 退出（服务起不来、额度耗尽、节点故障）才打 `CHAIN_STOP` 并停；判定行的结论不参与衔接条件。跑第一档的席位的链为「生成两遍 → 本席第二档分片 → 本席第三档分片」。**第一档与第二档的任何结论都不拦后续**：`GEN_REGRESS` 为 FAIL、NEED_RERUN 或 INVALID，`GATE2` 有差异、某模型新侧成功数为 0，都只记入报告，链照常走到第三档结束；已跑出的结果一律保留，不作废、不移走。主会话在第一档、第二档各自结束时出判定与差异表，收尾时汇成「用户决策项」一节。

**第三档**：`eval_manifest.py --mode v9-full --shards <席数>`；每席 `run_eval_gl.sh --dataset test-hard --max-steps 1600 --strict-cap --policies <模型>`；`eval_report.py` 出覆盖与视频判定。

**通用**

- GL 上的长任务在登录节点 tmux 里以 `launch_seat.sh` 形式启动（会话名前缀 `sgev-`），日志 `tee` 落盘并以 `EXIT_CODE=` 结尾；每份日志各挂一个监听，过滤词含 `EXIT_CODE=`、`RUN_BLOCKED`、`INFRA`、`svulkan2`、`EXCLUSIVE`、`Traceback`、`CUDA`。同时在跑的长 ssh 不超过 9 条。
- 每个席位起跑时打印并核对 `--dataset` 与 `--max-steps` 的配对（`test-hard0`↔1300、`test-hard`↔1600），不符即 `RUN_BLOCKED reason=step_cap_pairing`；这是启动参数的一致性检查，不是按档查表。每席收尾跑 `video_check.py`。
- 只有干活的 `srun` 带 `--gpu_cmode=shared`；跨 job 的 `srun` 先清 `SLURM_*` 变量。
- 本机常驻 `eval_video_mover.py` 把压缩视频与结果搬回 `artifacts/sg-evaluation/<run>/`，两端 sha256 相同才删 NFS 源。
- 从第一档起跑到全部结束，执行副本的 HEAD 冻结；文档改动在起跑前提交完。

## 六、预算

| 用途 | 乘式 | 轨迹 | reset 上限 |
|---|---|---:|---:|
| GL 第一档首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 | 177 | 531 |
| GL 第一档 smoke 与重跑 | 2 + ≤20（两集合共用，V9 优先） | 22 | 66 |
| 本机预检（非 Astra） | GroundSG 2 模型 × 3 局 + PonderPounce 4 局 | 10 | 20 |
| 本机预检（Astra） | ≤6 局 | 6 | 12 |
| 本机步数到顶 | 2 个数据集 × 1 局，不加载模型 | 2 | 4 |
| 预检修复后重跑 | 非 Astra 路线 13 条（生成 2、GroundSG 6、PonderPounce 3、步数到顶 2）× ≤2 局 | 26 | 78 |
| 本机第一档（旧码对新码） | 2 代码侧 ×（V9 43 格 × 3 局 + xhard0 16 任务 × 3 局） | 354 | 1062 |
| 本机第二档 GroundSG | 2 模型 × 2 侧 × 16 任务 × 1 档 × 12 局 | 768 | 1536 |
| 本机第二档 PonderPounce（CUDA 12 构建的本机环境） | 1 模型 × 2 侧 × 16 任务 × 1 档 × 12 局 | 384 | 768 |
| GL smoke（非 Astra） | 3 模型 × 3 路线 × 1 局 | 9 | 18 |
| GL 第二档 | 3 模型 × 2 侧 × 16 任务 × 1 档 × 12 局 | 1152 | 2304 |
| GL 第三档 | 3 模型 × 800 局（乘式见第一部分） | 2400 | 4800 |
| Astra 第二档 | 2 侧 × 16 任务 × 1 档 × 1 局 | 32 | 64 |
| Astra V9 连通 | 1 局 | 1 | 2 |
| 基础设施重试 | 非 Astra 每模型 ≤10 次（各席额度之和，不是每席 10 次）；Astra 0 | 30 | 60 |
| 到期续跑 | 非 Astra 3 模型 × ≤100 局（被 48 小时到期打断的在途局） | 300 | 600 |
| **合计** | | **5673** | **11925** |

评估每局按 build 与 reset 各 1 次计；正式成绩 3552 局（GroundSG 两组与 PonderPounce 各 1184）外加 Astra 32 局。正常 fail／timeout 不重试；smoke 不进正式分母；账本持久化，重启不重新获得额度。Astra 另有金额上限：本机预检与 GL 运行累计 30 美元（R4）。用户已于 2026-10-04 同意原表（「都同意」），并以原话第 26～31 条放行或提出新增的四行（预检修复后重跑、本机第一档、本机第二档、到期续跑）；超出本表的任何运行先停下申请。本机第一档按生成口径每局 reset 上限 3 次计。

## 七、风险与盲区

- **PonderPounce 的 CUDA 13 构建**：本机驱动 `570.211.01` 低于其要求的 580，本机改用同版本 torch 的 CUDA 12 构建，这个构建是否存在、能否跑通未验证；GL 驱动上能否加载未验证；**PaliGemma 分词器**需要访问许可；**显存**（官方称单服务至少 32 GB）与同卡仿真渲染能否共存于 A40 未验证。三项都在预检第一步暴露。
- **`flash-attn` 编译**在本机与 GL 节点架构上未验证；QwenVL 与 Astra 监视器都硬依赖它。
- **GL 计算节点到 OpenAI 的连通性**未验证（登录节点已通）；Astra 起跑前在节点上先查一次。
- **Astra 每局的规划次数**没有实测，估计每局 2～10 次、上限 24 次；记忆页多的任务请求体很大，接口对图像数量的限制未知。
- **第二档对 PonderPounce 的可比性**依赖固定会话号这一非官方默认行为；与官方的差别（固定会话号、GPU 渲染）写入报告。
- **新建的客户端扩展环境**可能出现依赖冲突，届时拆成两个环境，不动主环境。
- **第一档只证明生成链路未变**，不证明评估适配正确；评估适配靠 S3～S5 的固定输入测试与第二档报告。
- **两档都不阻塞的代价**：若第一档最终判为回归，第三档的 2400 局是在生成链路有变化的代码上跑出来的，是否采信、是否修复后重跑由用户在决策项里定；重跑不在本预算内。
- **上一轮环境敏感局** `MoveCube` xhard4 seed 23400200 已登记为抖动局，本轮仍可能再现，只报告。
- **本机第一档只是粗信号**：没有本机噪声基线，旧码与新码的逐局差异分不清是偶发抖动还是回归；正式结论只看 GL 第一档。
- **GroundSG 第二档的逐步一致只对每次起服务后的第一局有判别力**（服务端随机数跨局累积）；之后的局只读终态。
- **墙钟没有实测依据**：单局耗时要等预检；10 张卡、48 小时内跑不完时按「到期与续交」处理。组内配额紧张，近期可能只拿到 8 张卡甚至更少。
- **开工前卡先到会空转**：这是 R9 的已知代价。
- **上游源码未完整核实**：PonderPounce 的协议帧、观测键、依赖版本，Astra 的 `runner.py::main`、`run.sh` 细节，2026-10-04 审计时多数只拿到摘要；子模块入库后先逐条核对 1.4、1.5 的「官方行为」，不符处先改本计划再写代码。已直接读到源码并核实的只有 Astra `api_client.py`（429 最多 9 次发送、单次超时 180 秒、`STOP.json` 与 `api_started.json` 保护）和 PonderPounce 服务类的签名。
- **Astra 花费的单价未知**：`gpt-6-astra` 的价目开工后才查；30 美元够不够跑完 39 局没有依据，到线即停。
- **唤醒依赖会话存活**：会话关闭后没有任何东西会在排到卡时叫醒执行方。
- **审计留档**：2026-10-04 两份审计（本会话 workflow 报告在 `artifacts/sg-evaluation/plan-audit-20261004.md`，Codex 意见见当日会话）提出的问题已并入本版；其中约 20 条未经反驳验证的线索留在该报告第五节，实施到对应文件时顺带核对。
- 本计划的全部判定行均为待实施，没有任何一项已运行。

## 八、留档与提交

- `result.md` 另设「本机结果」一节（本机第一档的 `LOCAL_GEN_DIFF`、本机第二档的差异表），与 GL 的结论分开写，不参与成绩标注。
- `result.md` 设「用户决策项」一节：第一档两个集合的判定行与逐局定性、第二档每个模型的差异表摘要、Astra 两侧对比、预检与运行中记录的所有偏离，逐项写明「若不采信需要补做什么」。
- 档案名 `sg-eval-gl-<起跑日期>-01`，起跑前建 `docs/validation/<档案名>/launch.md`（冻结提交、第三方锁定、资产哈希、环境、席位清单、完整命令、预算、tmux 与 JobID 清单），跑完写 `result.md` 与 `records/`（判定行原文、清洗后日志、差异表、视频索引），并在 `docs/validation/README.md` 加一行。
- 一次性的 GL 侧脚本逐字归档到 `records/*.sh.txt`（上一轮 `launch.sh` 未入库的教训）。
- 子代理提交用 `sub/<编号>: ` 前缀，主会话 `--no-ff` 合并，每次合并后推送；主会话提交按 `12.<小版本>` 接续。
- 收尾：`scancel` 本轮清单内的 JobID，逐目录列名删除 NFS 暂存，核对 `squeue` 为空，输出 `EVAL_CLEANUP=DONE jobs_released=<n>`。
