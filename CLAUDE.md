# CLAUDE.md

本文件只写 **Claude Code 独有机制**的约定。仓库通用工作规则的唯一来源是 `AGENTS.md`，本文件不复述其任何内容。

@AGENTS.md

## 规则来源与优先级

- `AGENTS.md` 是本仓库通用规则的唯一来源，覆盖中文交流、计划范围、uv、改动后验证、tmux 长任务、稳定锚点、提交与推送、数据构建及评估留档、存储边界、性能测量和纯审计等规则。上面的 `@AGENTS.md` 显式导入其正文。
- **即便该导入失效，动手前也必须先完整读一遍 `AGENTS.md`。** 不假定 Claude Code 自动发现该文件，必须保留显式导入与完整阅读的兜底要求。
- 本文件只补 `AGENTS.md` 覆盖不到的 Claude Code 独有机制，共三块：Workflow 与 Agent 模型、Monitor 工具、plan mode 与计划文件。
- **动手前先做运行环境判定**：执行 `AGENTS.md` 的「运行环境判定（每次开工第一步）」中的只读检查，并在首次预检后的回复中说明本仓库实际环境；涉及数据或 GPU 时补查相应路径与设备，不套用来源仓库的环境分类。
- **两份文件冲突时一律以 `AGENTS.md` 为准**，本文件仅在 `AGENTS.md` 未规定处生效。

本文件按 [来源 CLAUDE.md](https://github.com/hongzefu/robomme_policy_learning_MotionJEPA/blob/028a77c59a442f047897f9736fc8acec0c050360/CLAUDE.md) 本地化；仅约束提供下述机制的 Claude Code，不把工具名称、模型选择或平台能力假定为 Codex 的能力。

## Workflow 与 Agent 模型（强制）

- **逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切 workflow 开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。
- **模型规则（2026-08-06 更新，按启动方式分两条）**：
  - **用 Agent 工具 launch 单个 subagent：强制 `model: "opus"`。**
  - **Workflow 脚本里调 `agent()`：默认且仅允许 `model: "sonnet"`。唯一例外**：workflow 收尾的总结/综合 agent、或负责制定计划（plan）的 agent，可用 `model: "opus"`，但**单次 workflow 内（按 workflow 计，不是按完整任务计——一个任务跑多个 workflow 时每个 workflow 各自计数）**累计使用 opus 不得超过 3 次。
  - 两条通用：禁止 haiku、fable 及一切白名单外模型。
- **同一进度点并行 spawn 不人为设上限**：同一轮决策下互相独立、无依赖的多个任务，用 Agent 工具并行 spawn subagent **不人为设置额外数量上限**，在平台实际能力和上级指令允许时一次性并行派发（在同一条消息里发出全部 Agent 调用，每个都按上条规则用 `model: "opus"`）。**仅限真正并行的场景**：后一个 agent 的输入依赖前一个的结果时保持默认串行机制，不为凑并行强行拆分——串行依赖本质上需要成倍等待时间，并行化不了。
- **反驳同一条不得并行多个 agent**：对抗验证 / 反驳类 workflow 里，**同一条 finding（同一条质疑、同一个待验证结论）只能派一个 agent 去反驳**，禁止对同一条并行派多个 agent 交叉反驳，也禁止同一条反复多轮反驳。不同 finding 之间照旧并行、不设数量上限（上条）。理由：反驳同一条的多个 agent 输入完全相同、彼此看不到对方产出，结论高度重复，只增成本不增信息；更糟的是会在综合阶段制造「多数票」假象——同一条被三个 agent 各自确认，读起来像三份独立证据，实际只是同一份推理被复制了三遍。
- **`model` 参数不得省略**：省略时会静默继承主会话模型（主会话常是 fable），同样算违规——每次派 agent 都必须显式写 `model`。
- **不设置任何额外并发限制**：`parallel()` / `pipeline()` 按需传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身管理实际并发上限，脚本层面不必也不应该叠加限制。

- Workflow 的 `log()`、阶段名称、进度与最终汇报遵守中文要求。若内部 agent 使用英文工作，每条派发提示词末尾必须附加：返回结果开头标注「[内部产出，英文]」，并提醒「以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。」

## Monitor 工具（强制）

本节只补 `AGENTS.md`「后台任务与会话清理」之外的 Claude 专用机制。tmux 启动、日志与行缓冲、结束信号、存活判断、会话清理均以该节为准，此处不重复。

1. **需要主动等待后台进程或日志事件时必须挂 Monitor 工具**（服务启动、测试运行、构建、部署、CI、日志变化），**严禁 `sleep` + 反复执行检查命令的方式轮询**。工具自动回报退出的情形按下文「谁必须挂 Monitor」处理；单次、时长确定且小于 3 秒的固定等待（如等一个文件落盘）可以直接等待。
2. **≤5 分钟的短任务**可直接前台运行；需要后台运行时用 `run_in_background` 启动，等待中间日志事件时挂 Monitor，单纯等待退出使用工具自带的自动回报。（较长任务按 `AGENTS.md`「后台任务与会话清理」启动。）
3. **谁必须挂 Monitor**：tmux 里起的任务 harness 感知不到其退出，**Monitor 是唯一完成信号，必须挂**；反之 `run_in_background` 直接起的进程退出时 harness 会自动重新唤醒，**不必再挂轮询去等它**。
4. Monitor 的 command 必须「挂在一个流上、有关心的行就发事件」，**禁止塞阻塞式 `while ...; do sleep N; done; echo 完成` 这种最后才输出一次的脚本**——末尾 echo 可能永远不执行，Monitor 就永远不汇报。正确形态是 tail 日志 + 过滤完成/报错行：

   ```bash
   tail -n +1 -F <仓库内日志绝对路径> | stdbuf -oL tr '\r' '\n' \
     | grep --line-buffered -E "全部完成|done|EXIT_CODE=|Error|Traceback|out of memory|找不到"
   ```

5. **一份日志挂一个 Monitor**，command 必须带过滤器（如 `grep --line-buffered`）、只输出关心的事件，不要全量转发整个日志；**禁止一条 `tail -F` 同时挂多个日志文件**——多文件 tail 每次切换都打 `==> 文件 <==` 头部行，实测噪声大到触发 Monitor 限流。
6. `AGENTS.md`「后台任务与会话清理」禁止裸 `pgrep -f` 判断进程存活，这条禁令**在 Monitor 里尤其致命**，原因是 pattern 字符串就写在 Monitor 自己那个 `bash -c` 的 argv 里，于是 pgrep 永远匹配到自己 → 条件恒真 → 永远「看起来还在跑」。确需按 pattern 匹配时，用括号技巧破坏自匹配：`pgrep -f "[g]enerate_swap_variants.py"`（正则 `[g]` 匹配字面 `g`，但自己 argv 里存的是 `[g]enerate`，匹配不到自己）。

## plan mode 与计划文件

- **请求计划批准只能走 `ExitPlanMode`**，不得在正文里问「这个计划行不行 / 要不要开始」，也不得用 `AskUserQuestion` 问批准。`AskUserQuestion` 只用于澄清需求或在多个方案间取舍。
- `AGENTS.md`「计划与授权范围」中「遇到范围、实现方式或破坏性操作存在歧义必须先询问用户」在 plan mode 下的落地方式是：**在 `ExitPlanMode` 之前用 `AskUserQuestion` 问清，不得带着歧义退出 plan mode。**
- 计划正文写进 harness 指定的计划文件（`~/.claude/plans/<slug>.md`），按 `AGENTS.md`「计划与授权范围」规定的结构组织（权威定义以 `AGENTS.md` 为准）：**第一部分给人看**（含 Context——为什么做这件事——与推荐方案概述；细节密度以 `AGENTS.md`「计划与授权范围」为准：少黑话，但关键机制与保证处给到代码级细节——命令、判定行、路径、实测数字内联，文件引用与步骤描述精确）；**第二部分技术细节供 agent 追踪**（含关键文件与验证方式等实现细节）。只写推荐方案不罗列所有备选。
- **纯文档改动的计划不分两部分**（`AGENTS.md`「计划与授权范围」的例外，权威定义以其为准）：本轮产出物只有仓库内 Markdown 文档改动时，计划文件写成一篇单一连贯叙述（为什么改 → 改哪个文件的哪一段 → 新正文逐段说明 → 验证与 commit），不再分「第一部分 / 第二部分」。
- plan mode 期间除该计划文件外一律只读：不改代码、不改配置、不 commit、不跑任何有副作用的命令。
