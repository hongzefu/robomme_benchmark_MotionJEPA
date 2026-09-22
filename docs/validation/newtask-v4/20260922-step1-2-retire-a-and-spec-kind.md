# V4 步 1～2：链路甲退役口径与新值规格类别

> 对应 [NEWTASK_RELEASE_V4_PLAN.md](../../../NEWTASK_RELEASE_V4_PLAN.md) 第六节步 1、步 2（红线 N1 要求的逐步报告）。
> 分支 `newtaskRelease-v4`，起点 `13e5151`。录像器 `RecordWrapper.py` 未改（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 为真）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `scripts/README.md` 第一节 1.0 | 追加「退役口径」：甲的 `candidates` / `rollout` 不再新增运行；代码、产物、相关测试原样保留 | 步 1 的闸门是「退役说明入 README、已进 Git 的产物零改动」；口径 1 与 N6 禁止改甲的代码，所以只写说明、不加运行时拦截 | `git diff --stat` 只含 README 一处；`scripts/injection/**`、`artifacts/injection/**` 零改动 |
| `src/robomme/robomme_env/utils/episode_spec.py::SPEC_KIND_NEWVALUE` / `spec_kind_for` | 新增 `native-newvalue/1` 类别；按难度决定类别：只有显式 `xhard` 走新值，其余（含不传）走 `native-parity/1` | 3.3③：新值与原值规格语义不同，必须分开，且不许互喂 | `test_spec_kind_follows_difficulty` |
| `episode_spec.py::SpecRecorder.__init__` | 新增 `difficulty` 形参；导出时写入对应 kind，回注时 kind 与本局难度不符即 `EpisodeSpecError` | 「两类不许互喂」 | `test_kinds_cannot_be_cross_fed` |
| `episode_spec.py::SpecRecorder.value` / `_mismatch` / `unattributed_mismatches` / `to_dict` | `value()` 新增可选 `decision_key`；新值模式的 mismatch 多带 `decision_key` 字段；`unattributed_mismatches()` 返回归不了因的不等（原值模式＝全部）；新值规格的 `provenance` 多一项 `unattributed_mismatches` | 3.3③：新值不等须归因到 `decision` 键，归不了因的才算 RNG 漂移 | `test_newvalue_mismatch_attribution`、`test_parity_mismatch_shape_unchanged`（原值 mismatch 仍只有 `path/drawn/frozen` 三键） |
| 十六个环境 `__init__` 里的 `SpecRecorder(native_episode_spec, ...)` | 追加 `difficulty=kwargs.get("difficulty")`（只读，不 pop） | 让记录器知道本局是否 xhard。十六处都在 `kwargs.pop("difficulty")` 之前，已逐文件核对 | 原三档不传或传 easy/medium/hard 时 kind 不变 |
| `src/robomme/robomme_env/utils/sampling_config.py::assert_native_decision`（新增 `_strip_xhard` / `_xhard_shape`） | 守卫分叉：去掉任意深度的 `xhard` 键后仍与原值逐键全等；`xhard` 子树只许改值、键结构须与源码申报一致；完全没有 `xhard` 条目的旧快照照旧放行 | 3.5：xhard 允许偏离，但只能偏离已申报的键；V6 组合覆盖与 G3 扫描要靠外部收窄 xhard 范围 | `tests/lightweight/test_v4_decision_guard.py` 五条 |

## 二、原值路径不变的论证

- 原三档：`spec_kind_for` 对 `None`/easy/medium/hard 恒返回 `native-parity/1`，导出文档、mismatch 形态、`provenance` 键集与 V3 逐字一致。
- 守卫：当前源码里还没有任何 `xhard` 条目进 `decision`，所以 `_strip_xhard` 对现有 decision 是恒等变换，判据与改前完全相同。
- 本步没有新增任何随机调用（N5 不涉及）。

## 三、测试

```bash
timeout 280 uv run --no-sync python -m pytest tests/lightweight/test_v4_decision_guard.py \
  tests/lightweight/test_episode_spec_recorder.py tests/lightweight/test_sampling_config_split.py -q
# 49 passed

timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
# 46 failed, 512 passed, 22 skipped, 74 deselected, 12 errors（122 s）
```

基线（`13e5151`）是 46 failed / 502 passed / 22 skipped / 12 errors；多出的 10 个 passed 就是本步新增的测试。
为确认 46 项失败与本步无关，在 `13e5151` 的临时 worktree 里单独复跑了出错的 8 个文件，结果同为 46 failed / 12 errors
（分布：`test_episode_action_sampling` 20、`test_native_sampling_config` 13、`test_candidates_refactor` 12 errors、
`test_candidate_loader` 4、`test_rollout_state` 4、`test_step_error_handling` 2、`test_TaskGoal` 2、`test_injection_migration` 1）。

## 四、推迟到后续步骤的事项

- `scripts/parity/train_split_audit.py::NEUTRAL_KEYS` 的 `demo_object_count` / `swap_speed_multiplier` 豁免，
  要等 VideoPlace*／两个 Swap 环境在 xhard 真正长出消费点后再撤（步 3b）；现在撤会让审计误报。
- 「decision 每个叶子键须在 trace 里至少消费一次」的检查放到步 5 的 V3g 工具里做。
- `train_split_worker.py` 目前把 `recorder.mismatches` 原样落盘；新值局要改看 `unattributed_mismatches()`，放步 5。
