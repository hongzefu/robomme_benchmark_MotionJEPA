# Claude Code 专属约定

> 本仓库的**通用**约定（简体中文、uv、端到端测试、后台任务的 tmux 起法、禁硬编码行号、patch 级可视化、git commit、`/data` 本地盘优先、计划分两部分）全部在根目录 [`AGENTS.md`](AGENTS.md) 的「强制规则（最高优先级）」里，**必须完整阅读并严格遵守**，本文件不重复。
> 本文件只收 **Claude Code 特有、AGENTS.md 不覆盖**的条目，与 AGENTS.md 同等强制；两者冲突时以 AGENTS.md 的「强制规则（最高优先级）」为准。

## 1. 最终输出层一律中文（AGENTS.md 规则 1 的 Claude Code 展开）

- **本约束对"给用户看的最终输出层"一视同仁，无任何例外**：Ultracode / Workflow 编排、`/code-review`、fork 会话、background 任务、以及任意 subagent 派生内容，最终落到用户眼前的叙述/总结/状态汇报/计划/提问必须是中文。具体要求：
  - **最终面向用户的总结、状态汇报、计划、提问一律中文。** 长任务收尾汇报最容易漂成英文，重点盯住。
  - **Workflow 的 `log()` 进度叙述、phase/agent 的 `label`、给用户看的 narrator 行用中文。**
  - **Workflow 内部（`agent()` 派发的 subagent）默认允许用英文工作**，但每条 `agent()` prompt 末尾必须附加固定提示词，要求该 subagent 在返回结果开头标注"[内部产出，英文]"并提醒消费方："以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。"

## 2. 等待后台进程一律用 Monitor（AGENTS.md 规则 4 的 Claude Code 展开）

- **等待任何后台进程（生成、合并、测试、日志变化）一律用 Monitor。Monitor 要"挂在一个流上、有关心的行就发事件"，禁止塞 `while ...; do sleep N; done; echo 完成` 这种最后才输出一次的阻塞脚本。** 正确形态是 tail 日志 + 过滤完成/报错行（`tr` 需 `stdbuf -oL` 防管道缓冲吞行）；**一份日志挂一个 Monitor，禁止一条 `tail -F` 同时挂多个日志文件**（实测多文件 tail 每次切换都打 `==> 文件 <==` 头部行，噪声大到触发 Monitor 限流）：
  ```bash
  tail -n +1 -F /path/to/run.log | stdbuf -oL tr '\r' '\n' \
    | grep --line-buffered -E "全部完成|EXIT_CODE=|Error|Traceback|out of memory|找不到"
  ```
- **进程存活检测禁止用裸 `pgrep -f "<pattern>"`**（pattern 在 Monitor 自身 argv 里 → 永远自匹配恒真）。tmux 起的任务用 `tmux has-session`；其余用括号技巧 `pgrep -f "[g]enerate_swap_variants.py"` 或启动时 `$!` 记下的具体 PID。
- **`run_in_background` 直接起的进程退出时 harness 会自动重新唤醒，无需再挂 pgrep 轮询；但 tmux 里起的任务 harness 感知不到退出，Monitor 是唯一完成信号，必须挂。**

## 3. Workflow 三条约定

**Workflow 只有三条约定，其余全部作废：**
- **①逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。
- **②模型规则（2026-08-06 更新，按启动方式分两条）**：**用 Agent 工具 launch 单个 subagent 时强制 `model: "opus"`**；Workflow 脚本里调 `agent()` 默认且仅允许 `model: "sonnet"`，**唯一例外**：workflow 收尾的总结/综合 agent、或负责制定计划（plan）的 agent，可用 `model: "opus"`，但**单次 workflow 内（按 workflow 计，不是按完整任务计——一个任务跑多个 workflow 时每个 workflow 各自计数）**累计使用 opus 不得超过 3 次。两条通用：禁止 haiku、fable 及一切白名单外模型，且 **`model` 参数不得省略**——省略会静默继承主会话模型（常是 fable），同样算违规。
- **③不设置任何额外并发限制**：`parallel()`/`pipeline()` 直接传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身已有并发上限（`min(16, cpu核数-2)`），脚本层面不叠加限制。
