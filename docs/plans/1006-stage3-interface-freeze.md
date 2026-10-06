# 1006 第三阶段共享接口冻结说明

> 依据：根目录 `1006-rename-official-names-and-stage3-eval-plan.md`（下称「计划」）第二部分二节「子代理分配表」中「主会话冻结共享接口（CLI、seat_info、seed／cap、预算 token、trace／NPZ 与发布索引字段）」一句。本文件由主会话写定，R2／R3／R5／R6／R7／R4 各子代理按本文件实现，**不得自行改字段名或语义**；确需改动时停下交回主会话。名字一律用 R1 改名后的新名（`groundsg`、`perceptual-framesamp-modul`、`framesamp_modul`、`ood`、`hard-verify`）。
>
> 冻结时的代码基点：R1 改名合入后的工作分支 HEAD（派发提示里给出完整 sha）。

## 一、合并顺序（相对计划的调整）

计划写的顺序是 R1 → R2 → R3 → R6 → R7 → R5 → R4。本文件把 **R6（trace／语言账本接口的提供方）提到 R2 之前**：R2／R3／R5 都要调用 R6 新增的 `LanguageLog` 与数组合并写函数，先合提供方，后合调用方，每次合并后的核心短测才不会因为「调用了尚不存在的接口」而失败。实际顺序：**R6 → R2 → R3 → R7 → R5 → R4**。R4 在前五块全部合入后再派（测试针对真实代码写，不针对设想写）。

## 二、CLI 与参数传递

### 2.1 数据集与步数配对（R3：`run_seat.sh::step_cap_pairing`、`run_official_hard.sh`；R5：`astra_hard_runner.py::DATASET_STEP_PAIRING`）

| 数据集 | `--max-steps` | `strict_cap` |
|---|---|---|
| `ood` | 1800 | 1（第 1801 次 `step` 在进入真实环境前被拒，置 `cap_hit=True`，终态 `timeout`） |
| `hard-verify` | 1300 | 0（不变） |

不符一律打印 `RUN_BLOCKED reason=step_cap_pairing` 退出 3。生成规格 `hard_specs.py::EXEC_CAP=1600` 不动。

### 2.2 模型种子 `--policy-seed <int>`

- 入口：`run_eval_gl.sh`、`run_seat.sh`、`env_client.py run`（R3）；`run_official_hard.sh`、`official_hard_runner.py`（R2）；`run_astra.sh`、`astra_hard_runner.py`（R5）。**必填**，缺失即 `RUN_BLOCKED reason=policy_seed` 退出 3（不回落任何旧默认值）。值为非负整数。
- 服务端（R3）：
  - GroundSG／FrameSamp：`policy_server_wrap.py`（新增，包锁定三方 `third_party/mme-vla/scripts/serve_policy.py`）收到的 `--seed=<policy_seed>`；`run_seat.sh::build_server_cmd` 与原侧启动链都改走它。
  - SimpleMemVLA：`smvla_server.py serve --policy-seed <n>`，`reseed()` 用该值替代常量 `EPISODE_SEED=0`（生命周期不变：加载后一次、每局 `new_episode` 前一次）。
  - PonderPounce：`--args.seed <n>`（原来固定 0）。
  - 服务启动后写 `server-metadata-<port>.json`（SimpleMemVLA 已有；其余由外壳写），至少含 `{"policy_seed": n, "argv": [...], "pid": …}`，供验收反查。
- 客户端（R2）：`official_defs.make_args(..., model_seed=policy_seed)` 显式设 `Args.model_seed`；QwenVL／MemER 预测器构造前调用 `official_defs.seed_everything(policy_seed)`（`random`、`numpy`、`torch`（若可导入）三处）。Astra（R5）：服务 `--seed=<n>`，云端 planner／monitor 无 seed 接口，只记录不伪造。
- 结果行、trace header／identity、`render.json` 都记 `policy_seed`（见第四节）。

### 2.3 GroundSG 变体与 MemER adapter

- 参数名（R1 后）：`--groundsg-variant {ground-sg-oracle,ground-sg-qwenvl,ground-sg-memer}`；新增 `--memer-adapter <dir>`（R3 管席位脚本与 `env_client.py`，R2 管原侧两入口）。
- 配对规则：`ground-sg-qwenvl` 必须且只能给 `--qwenvl-groundsg-adapter`；`ground-sg-memer` 必须且只能给 `--memer-adapter`；目录不存在或配错即 `RUN_BLOCKED reason=variant_pairing`。
- `official_defs.py`（R2）：`VARIANT_MEMER = "ground-sg-memer"`，`VARIANTS = (VARIANT_ORACLE, VARIANT_QWENVL, VARIANT_MEMER)`；`make_args(..., memer_adapter_path=…)` 写 `Args.memer_adapter_path`；`assert_one_predictor` 改为三者恰一真且 `use_gemini` 为假。

### 2.4 预算参数（R3 新侧、R2 原侧）

- `run_eval_gl.sh`、`run_official_hard.sh` 新增必填：`--budget-ledger <path> --trajectory-cap <n> --shared-infra-cap <n> --expired-cap <n> --planned-first-tries <n>`，原样转发到每个消费者（`run_seat.sh` → `env_client.py run`；原侧 → `official_hard_runner.py`）。任一缺失 → `RUN_BLOCKED reason=budget_args` 退出 3；**不回落 `budget_ledger.py` 的常量默认值**。本轮取值 `870 / 50 / 50 / 821`。
- `--reset-budget` 改为可选：不给时只计量（经共享账本 `claim_reset` 告警），不抛 `ResetBudgetExhausted`；给了仍按旧语义硬拦（保留兼容，本轮不给）。`--infra-retry-budget` 保留。

### 2.5 `seat_info`（`env_client.py::SeatRunner.seat_info`，R3）

在现有键之外新增：`policy_seed`、`groundsg_variant`（原 `mme_variant` 键 R1 已改名）、`memer_adapter_path`、`budget_ledger`、`effective_cap`。仍只在进程内传给 `make_policy_context(seat_info)`，不落盘。

## 三、预算账本（R3：`budget_ledger.py`；消费者 R3 新侧、R2 原侧）

1. **配置行**：账本首次打开时若无 `kind=config` 行则写一行 `{"kind":"config","trajectory_cap","shared_infra_cap","expired_cap","planned_first_tries","schema":"sgeval-budget/2"}`；之后每次打开比对，构造参数与配置行不一致 → 抛 `BudgetConfigMismatch`（CLI 退出 3）。
2. **route**：`<policy_label>/seed<policy_seed>/<side>`，`side ∈ {new, orig}`；GroundSG 为 `groundsg/<variant>/seed7/new`。旧 route 只在读历史时经 `official_defs` 别名表映射。
3. **幂等 token**：`token = f"{route}|{key}|a{attempt_no}"`。`reserve(..., token=)`：同 token 已有未 release 的 reserve 行时返回同一 rid、不写新行；`claim_retry(..., token=)`：同 token 已领过时返回 True、不写新行；`AttemptLedger.attempt_start` 行记 `token`。崩溃后续跑用同一 token 恢复，不重复扣额。
4. **首试保留额度**：`reserve(..., kind_of_try="first"|"recovery")`。recovery 仅当 `已用轨迹 + 1 + (planned_first_tries − 已开始的首试数) <= trajectory_cap` 时允许，否则 `BudgetExhausted(reason="reserved_for_first_tries")`；infra 与 expired 的 recovery 合计另受 `trajectory_cap − planned_first_tries`（本轮 49）约束，分项各自不超过 `shared_infra_cap`／`expired_cap`。
5. **分片排他 lease**：`BudgetLedger.lease(shard_id) -> contextmanager`，在 `<ledger>.lease.<shard_id>` 上 `fcntl.flock(LOCK_EX|LOCK_NB)`，进程存活期间持有；拿不到 → `RUN_BLOCKED reason=lease_held` 退出 3。`SeatRunner` 在读取 pending 身份**之前**取得。
6. **坏行即拒**：`_append` 写前若文件末字节不是 `\n` 先补换行；每次读写前 `bad_rows > 0` → 抛 `LedgerCorrupt`（退出 3），不再只在收尾报 FAIL。
7. 原侧（R2）直接 `import budget_ledger`（经 `load_sibling`）调用同一套 `reserve／claim_reset／claim_retry／commit／release`，不再经 `orig_budget.py` 子进程。

## 四、trace 与完整数值（R6：`trace_writer.py`、`recorder.py`）

1. **header 行**新增 `policy_seed`、`effective_cap`；**identity** 必含 `attempt`（原侧 R2 补）与 `policy_seed`；**end 行**新增 `policy_seed`，原侧补 `steps_attempted／steps_observed／frames_recorded`（R2）。
2. **step 行**可选新增 `source_call_id`、`chunk_index`（语言账本关联，见第五节）；不传时 step 行键集合仍为旧 9 键（`test_default_log_step_bytes_unchanged` 不得破坏）。
3. **完整数组**：`TraceWriter` 构造新增 `arrays_path=None`（缺省 `<trace 同目录>/arrays.npz`）。`log_step`／`log_missing_step` 收集 `exec_action__%05d`（键号 = step−1，每个 attempted 步都有）；观测步另收 `exec_state__%05d`（缺观测步不补零，记入 end 行 `arrays.missing_state_steps`）。`close()` 调 `merge_write_npz(path, mapping)` 写盘，end 行新增 `arrays = {"path":"arrays.npz","action_keys":n,"state_keys":m,"missing_state_steps":[…]}`。
4. **`trace_writer.merge_write_npz(path, mapping) -> None`**（新增，唯一允许的 `arrays.npz` 写法）：读已有文件 → 同键须 dtype／shape／sha256 全同，否则抛 `ArraysConflict` → 合并 → 写 `path.tmp` 后 `os.replace`。`recorder.py::EpisodeRecorder._write_arrays`、`smvla_client.py`、`pp_client.py`、`astra_hard_runner.py::write_exec_actions`、`orig_observer/step_arrays.py` 的直接 `np.savez` 一律改成调它（R6 改前三个；Astra 由 R5 改；`step_arrays.py` 由 R2 改）。于是关闭先后不再互相覆盖。
5. 判定行（R7 检查器）：`TRACE_ARRAYS=PASS episodes=<n> attempted_steps_missing=0 observed_state_missing=0`。

## 五、语言账本 `language.jsonl`（接口 R6；接线：R2 GroundSG 三变体与原侧，R6 FrameSamp／SimpleMemVLA／PonderPounce 客户端，R3 三个服务外壳回包，R5 Astra，R7 比较器与检查器）

`trace_writer.LanguageLog(path)`，path 固定为 `<trace 同目录>/language.jsonl`，每行 `ensure_ascii=False`、写后 `flush`。方法：

| 方法 | 写的行 |
|---|---|
| `open_call(model, step, *, params=None, transport_attempt=0, retry=0) -> call_id` | `{"kind":"call_open","call_id","model","step","params","transport_attempt","retry","ts"}` |
| `message(call_id, *, dir, role, text, images=None, channel=None, token_ids=None, mask=None, tokenizer=None, truncated=None, demo_video=None) -> message_index` | `{"kind":"message","call_id","message_index","dir","role","text","images","channel","token_ids","mask","tokenizer","truncated","demo_video","ts"}`；**`dir=in` 的消息必须在真实发送前写入** |
| `close_call(call_id, *, status, parsed=None, fallback=None, server_final_text=None, server_truncated=None)` | `{"kind":"call_close","call_id","status","parsed","fallback","server_final_text","server_truncated","ts"}`，`status ∈ {reply, error, cancelled}` |
| `reuse(step, reused_call_id)` | `{"kind":"reuse","step","reused_call_id","reused_previous":true}`（QwenVL keep_period 复用步） |
| `close()` | 对仍未关闭的调用补 `call_close status=cancelled`，再关文件 |

- `model ∈ {subgoal_model, action_model, planner, monitor}`；`role`：`system`／`user`／`assistant`（回复）／`fields`（动作模型结构化输入）。
- `images` 元素：`{"slot","ref","phase","frame_idx","cam","raw_sha256","sources","transform","encoded_sha256"}`，`ref ∈ {keyframe, recent, current, wrist, command_start, demo_sheet, memory_sheet}`，`phase ∈ {demo, exec}`，`cam ∈ {front, wrist}`；不存图片本身。
- 执行步关联：调用方在 `TraceWriter.log_step(..., source_call_id=, chunk_index=)` 记录动作来源调用。
- `fallback ∈ {null, last_valid, model_response_error, continue_last}`；MemER 重问的每次提问各开一个调用，`retry` 取 0／1／2。
- **服务外壳回包审计键**（R3 写入，客户端读取）：服务回包 dict 增加键 `"_sgeval_audit"`，值为 `{"channels":[{"channel":"task"|"symbolic","text","token_ids","mask","tokenizer","truncated"}], "server_final_text": str|None, "pp_generation": {...}|None}`。客户端在把动作交给环境前 `pop` 掉该键并记入语言账本；缺该键时（旧服务、Oracle 原侧）记 `server_final_text=None` 不报错。外壳必须只观察真实结果，不得多推理、多抽随机数（`OBS_EQ` 闸门，R4 测）。
- 判定行（R7 检查器）：`LANG_IO=PASS episodes=<n> unresolved_steps=0 open_calls=0 image_ref_unresolved=0`。

## 六、媒体发布索引（R7）

- 布局：`<run 根>/<model_id>/seed<policy_seed>/[oracle|qwenvl|memer/]videos/<task>_ep<N>_<success|fail|timeout>_<task_goal>_<tier>.mp4`；`model_id` 取策略标签（`perceptual-framesamp-modul`、`smvla`、`pp`、`groundsg`、`astra`）。
- 只发布账本 `accepted_attempt_id` 对应的那次 attempt；strict-cap 命中命名 `timeout`；超 255 字节沿用 `safe_filename` 截断加哈希。
- 索引 `<…>/videos/index.tsv`，列：`model_id policy_seed dataset side key accepted_attempt_id episode_id terminal src_rel src_sha256 dst_name`；同名同 sha 重复发布幂等跳过，同名异 sha → FAIL。
- 判定行：`VIDEO_LAYOUT=PASS model=<m> seed=<s> videos=<n> error_named=0`；无帧 error 局只进索引（`dst_name` 为空）、不出视频，口径 `accepted = videos + no_frame_error`。

## 七、结果行（results.jsonl）新增字段

`policy_seed`、`effective_cap`、`policy_variant`（含 `ground-sg-memer`）、`memer_compat_sha256`（MemER 才有）、`server_seed`（从服务元数据反查）、`error_kind`（`model_response_error` 等具名错误）、`budget_token`。

## 八、执行期限与无进展监督（R3）

- `env_client.py run` 新增 `--context-deadline-s`（缺省 1800）、`--first-infer-deadline-s`（缺省 1800）、`--media-deadline-s`（缺省 1200）；超期以 `infra_reason=deadline_<phase>` 结束本局。
- `progress.json` 增加 `phase ∈ {context_load, first_infer, episode, media_finalize, done, finished}`、`identity`、`step`、`t`；`run_seat.sh::idle_s` 改读 `progress.json` 的 `t` 与 `step` 变化，不再看 `client.log` mtime。
- 客户端／服务重启计数持久化到 `<ledger-dir>/<label>.recovery.json`（`{"client_restarts","server_restarts","noprog_restarts"}`），续跑沿用，不清零。

## 九、比较器（R7）

`gate2_compare.py --expect-host <name>`：逐行核两侧 `host`（或 `node`）都等于给定主机，未知或跨机 → `GATE2_PROVENANCE=FAIL`；不给时保持 GL 模式原检查。另读两侧 `language.jsonl`，按 `(call 序号, message_index)` 对齐逐次比 `text`，`GATE2` 行多报 `prompt_diff=<n> reply_diff=<n>`。
