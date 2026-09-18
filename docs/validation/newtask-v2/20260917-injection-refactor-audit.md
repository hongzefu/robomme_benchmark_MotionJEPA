# 注入重构计划对抗审查

结论：当前计划未通过对抗验证；以下九项问题应在相应实施阶段前修订。没有实施重构，也没有迁移、删除或重新生成运行 10 的数据。

审查对象为 `newtask-v2.1refractor` 分支 `e35d7f3` 的 [INJECTION_REFACTOR_PLAN.md](../../../INJECTION_REFACTOR_PLAN.md)，证据来自当前源码、运行 10 的 JSON/JSONL、一个只读 HDF5 反例及定向测试。计划原文保持不变。用户指令原话：「/data/hongzefu/robomme\_benchmark\_MotionJEPANewTask/INJECTION\_REFACTOR\_PLAN.md」「对抗验证正确性」。

## 一、规格散列契约不符合实际代码（P1）

计划第四节 4.1 称 `spec_sha256` 只覆盖 `layout / objects / actions`，第二部分红线 R4 又要求算法与作用域不变。但 `scripts/injection/specs.py::record_sha256` 和 `scripts/generate_dataset_newseed.py::spec_record_sha256` 实际上仅排除 `spec_sha256 / collision`，会散列其余全部键，包括 `task / difficulty / episode / sampling_cells`。

实测运行 10 的 RouteStick/easy/ep0 原记录合法；直接加计划规定的 `record / block / seed / split / role / error_type / screening` 后，旧散列 `137749dc…` 重算成 `4c6860f8…`，`validate_episode_spec` 抛出 `EpisodeSpecError: spec_sha256 不符`。回写 `role` 也会继续改变散列。只搬模块、只增加 JSONL 读法不足以满足计划。

修订要求：明确定义候选外层元数据与旧规格原文的分离/投影，先恢复旧记录再调用旧校验与环境接口；完整保留旧散列覆盖字段。加载器等价验收应比较投影后的记录，并覆盖角色回写后的再次加载；不能通过重新计算全部旧散列来绕过 L1。

## 二、逐条拒绝证据不能从现有聚合统计恢复（P2）

计划第二部分逐文件表规定 `specs.py` 等四个核心模块“只改 import 路径”，`screen.py` 在组级计算后填每条 `candidates_tried / rejected_before_accept`，并输出逐条拒绝明细。现有 `specs.py::_place_binfill_cubes` 只累计组级/块级计数，几何拒绝直接 `continue`，不保存 episode 对应的拒绝记录；`_count_rejection` 对其他碰撞也只保留前 64 个样本。

运行 10 的 BinFill/medium 有 `candidates_tried=5281`、`rejected_geometry=3184`，`rejection_samples=[]`，候选行没有逐条尝试计数。不能把 5281 当成尝试了 5281 条完整 episode：这里按每个方块的摆放尝试累计。组级总数不能唯一还原每条候选的拒绝次数与拒绝内容。

修订要求：在生成循环中增加不改变随机数消费的观测记录，明确按物体尝试还是按整条 episode 统计，并用 L1 验证原规格不变；历史迁移无法恢复的字段标记不可用，不能编造零值或宣称全量明细已保留。若依靠重算恢复，应明确重算及采集机制，而非从旧聚合数据推断。

## 三、`--only-unused` 与原停点规则冲突（P1）

计划第五节 5.2、阶段 5 要求检查全部 838 条 unused，并保持原 700 条 primary；第二部分 `reset_check.py` 条目却规定“不改停点规则”。现有 `env_check.py::_GroupState.satisfied` 在 `passed >= need` 时成立，`next_episode` 随即停止派发，`need` 为每组 50。

复用当前状态类及 40 worker 批调度，在全部候选均通过的纯内存反例中，原流程复现 `scheduled=720 unused_left=838 shortfall=0`；只给 unused 则为 `scheduled=600 unused_left=238 shortfall=131`。六个较大的剩余候选组提前停止，八个不足 50 条的组又被错误判缺口。

修订要求：把“执行全部选定 unused”的终止条件与“前 50 条通过者的交付角色”分离；原 primary 冻结，新增通过者只成为 spare。不能复用每组攒够 50 即停作为此次补查的完成条件。

## 四、对拍命令缺少状态隔离，并重复执行 reset（P1）

计划第五节 5.3 要求收尾回写输入 `candidates.jsonl` 的角色；第二部分 runbook 的两个临时 `$PID` 命令却都把 `--candidates` 指向正式 `$RID` 的候选文件。临时运行只生成 210 条，正式 train 有 1842 条：其余 1632 条在临时结果中不存在。整体重算角色会污染旧运行，保留旧角色又不能满足临时运行的全局 `ROLES_CONSISTENT`。

同一 runbook 先调用完整 `rollout`，而其既定顺序已经包含 `reset_check`，之后又单独调用一次 `reset_check`。来源 `env_check.py::run_env_check` 每次创建新状态，并用追加方式写行，计划没有去重或续跑约定。照搬会对同一 720 个键写出 1440 行；对拍若先转字典可能掩盖重复。

修订要求：临时运行使用自己的候选副本或明确的只读输入模式，禁止回写正式候选；定义部分运行的验收作用域及 pending 行；reset 只执行一次或实行幂等合并。对拍先检查预期键集合、缺失、额外及重复键，再比较字段。

## 五、数轴的 1796 条验收与慢条剔除冲突（P1）

计划第九节 L2、阶段 3/6 都把 timeline 的 episode 数固定为 1796。旧 `window_timeline.py::extract` 调用 `apply_slow_exclusion` 后，`episodes` 是保留条数，剔除前数量另存 `episodes_before_exclusion`。

只读实测运行 10 的 VideoUnmaskSwap/xhard/ep5：`ok=True`、总长 1312 帧，最长子目标段 828 帧；旧函数明确返回「单段 828 帧 > 400」。因此保持原规则时，基线保留条数至多 1795，不能满足 `episodes=1796`。

修订要求：分别核对 `episodes_before_exclusion=1796`、`kept+excluded=1796`、读入失败数为零，以及 `excluded_slow` 的键与原因一致；完整保留剔除规则。尚未跑全量 extract，不能把“至多 1795”写成精确保留数。

## 六、产物迁移缺少有效路径改写（P1）

阶段 4 先生成结果、阶段 6 生成 timeline，阶段 7 再把 `feasibility/P01x20/<task>/<diff>` 移至 `rollout/<task>/<diff>`，迁移条目只列目录移动和散列核对。

现有正式结果中，旧前缀出现在 `h5_path` 1796 次、`video.path` 1821 次、`binfill_demo.video_path` 438 次、`video.no_object_paths[]` 127 次；timeline 也保存 `source / h5_path`。只移动文件，即使新位置的 `H5_INTACT` 通过，结果行仍会指向不存在的文件，违反第四节“只用 jsonl 和 h5 判断成功”的存在性规则。新 `windows.py` 若提前按新目录硬定位，阶段 6 也会在目录尚未迁移时失败。

修订要求：规定旧根到新根的路径映射和生效时机，对新用户入口中的全部有效路径进行改写与存在性校验；历史日志可以保留原文。迁移闸门还需覆盖 mp4、附加视频和元数据清单，不能只数 h5。

## 七、删除清单未闭合测试与保留工具的依赖（P1）

计划第八节和阶段 8 要删除 `campaign.py / contract_build.py / injection-before-2d/`、旧契约，并搬走其他模块；逐文件清单没有测试适配。

当前至少九个 lightweight 文件引用这些旧模块/文件。例如 `test_injection_contract.py` 在顶层导入 `contract_build` 并加载 v1/v2，`test_injection_campaign.py` 导入 `campaign`，`test_window_timeline.py` 加载旧目录。`tests/_shared/native_sampling_parity.py` 顶层还导入 `scripts.injection.h5_compare`，会连带破坏保留的原值对拍及其 dataset 测试。不能用文档搜索零命中代替导入依赖检查。

修订要求：补逐文件的测试迁移/退役清单，保留对应有效断言；对保留的原值对拍改导入路径。阶段 8 必须能正常收集 lightweight 测试，并通过本轮涉及的测试。当前短测通过只证明删除前状态。

## 八、`.gitignore` 漏收日志、漏排 smoke 大文件（P1）

第二部分拟替换段没有恢复日志的规则，但当前文件前文存在全局 `*.log`，因此新 `candidates/logs/plan.log` 等仍被忽略，与“logs 照常进 git”相矛盾。旧注入段原有 `!/artifacts/injection/*/logs/*.log`，整体替换会删掉它。

新 h5/mp4 忽略规则只匹配 `rollout/<task>/<diff>/...`；计划规定 smoke 落在 `rollout/logs/smoke/<task>/<diff>/...`，多了两级，不能命中。原来的递归 h5/mp4 兜底也会随整体替换删除。

修订要求：显式恢复两阶段日志，并递归排除 rollout 下 h5/mp4，包括 smoke。用代表性的正式、失败、smoke、日志路径运行 `git check-ignore --no-index -v` 核验后再暂存。本项基于实际规则与拟替换规则的静态匹配，未修改 `.gitignore`。

## 九、BinFill 仅比帧数不能验证视频一致（P2）

计划第九节对 BinFill 视频只比帧数。现有运行 10 的 BinFill/medium/ep1 与 ep16 都有 1388 帧，记录的视频 SHA-256 分别为 `1454cb7ed125faf9…` 和 `fe38f2b95fe662981…`，对应任务目标不同。ep1 在方案 B 内；保持它的 h5 不变，把视频错配为 ep16，计划的视频判据仍会通过。

修订要求：先确定编码是否稳定；若容器散列确实不稳定，改比解码后逐帧内容，并检查 demo/exec 边界和红框。只比帧数的结论必须限定为长度一致。方案 B 含 43 条成功 BinFill，不能把这 43 条的视频内容等价标为已证明。此处依据已存视频元数据构造反例，未重新解码这两条视频。

## 复核命令与实测结果

在仓库根目录执行。下列探针只读源文件和现有数据，不启动环境，不写运行 10。

### 规格散列反例

```bash
command -v uv && uv run --no-sync python - <<'PY'
import copy
import json
from pathlib import Path
from scripts.generate_dataset_newseed import validate_episode_spec, EpisodeSpecError
from scripts.injection.specs import record_sha256

root = Path('artifacts/injection/20260912-contract-v3-10')
row = json.loads((root / 'specs/RouteStick/easy.json').read_text())['episodes'][0]
validate_episode_spec(row, row['task'], row['difficulty'], '旧候选')
candidate = copy.deepcopy(row)
candidate.update(record='candidate', block=0, seed=16000, split='train',
                 role='pending', error_type=None, screening={'geometry': 'PASS'})
print('旧散列', row['spec_sha256'])
print('新行重算散列', record_sha256(candidate))
try:
    validate_episode_spec(candidate, row['task'], row['difficulty'], '新候选')
except EpisodeSpecError as exc:
    print(type(exc).__name__, str(exc))
else:
    raise AssertionError('未触发预期反例')
PY
```

实测旧记录校验通过，新记录抛出上述散列错误；捕获预期异常后探针退出 0。

### unused 纯状态反例

```bash
command -v uv && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python - <<'PY'
import json
from pathlib import Path
from scripts.injection.env_check import EnvCheckPlan, _GroupState

root = Path('artifacts/injection/20260912-contract-v3-10')
groups = json.loads(Path('scripts/configs/newtask-v2/delivery_400.json').read_text())['groups']

def count(only_unused):
    states = []
    for group in groups:
        task, difficulty = group['task'], group['difficulty']
        document = json.loads((root / 'specs' / task / f'{difficulty}.json').read_text())
        checked = {json.loads(line)['episode'] for line in
                   (root / 'env_check' / task / f'{difficulty}.jsonl').read_text().splitlines()}
        episodes = [row['episode'] for row in document['episodes']
                    if not only_unused or row['episode'] not in checked]
        states.append(_GroupState(EnvCheckPlan(task, difficulty, group['run_episodes'], 50), episodes))
    total = 0
    while True:
        batch = []
        while len(batch) < 40:
            grew = False
            for state in states:
                if len(batch) >= 40:
                    break
                episode = state.next_episode()
                if episode is not None:
                    batch.append((state, episode))
                    grew = True
            if not grew:
                break
        if not batch:
            break
        for state, episode in batch:
            total += 1
            if not state.satisfied:
                state.passed += 1
    return (total, sum(len(s.pool) - s.cursor for s in states),
            sum(max(0, s.plan.need - s.passed) for s in states))

print('ORIGINAL_ALL_PASS scheduled=%d unused_left=%d shortfall=%d' % count(False))
print('ONLY_UNUSED_ALL_PASS scheduled=%d unused_left=%d shortfall=%d' % count(True))
PY
```

实测分别输出 `720 / 838 / 0` 与 `600 / 238 / 131`，退出 0。

### 数轴剔除反例

```bash
command -v uv && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python - <<'PY'
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('audit_windows', 'scripts/injection-before-2d/window_timeline.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
path = Path('artifacts/injection/20260912-contract-v3-10/feasibility/P01x20/episode_results.jsonl')
rows = [json.loads(line) for line in path.read_text().splitlines()]
row = next(row for row in rows if (row['task'], row['difficulty'], row['episode']) ==
           ('VideoUnmaskSwap', 'xhard', 5))
episode = module.read_episode(Path(row['h5_path']))
print('生成成功', row['ok'], '总帧数', episode['total'], '最长段', module.max_segment(episode))
print('独立于组中位数的剔除原因', module.exclusion_reasons(episode, group_median=10**8))
PY
```

实测总长 1312、最长段 828，命中 400 帧阈值，退出 0。极大中位数仅用于隔离这个独立条件。

### 定向测试与静态依赖检查

```bash
command -v uv && timeout 240s uv run --no-sync python -m pytest \
  tests/lightweight/test_episode_specs.py tests/lightweight/test_env_check.py \
  tests/lightweight/test_injection_delivery.py tests/lightweight/test_injection_blocks.py -q
rg -n 'scripts\.injection|injection-before-2d|injection_contract_v[12]' tests --glob '*.py'
rg -n 'def record_sha256|def _place_binfill_cubes|def _count_rejection|rejected_geometry' scripts/injection/specs.py
```

定向测试退出 0：`65 passed, 9 skipped, 2 warnings in 5.24s`。九个跳过项需要历史冻结产物；本轮没有补建，也没有把跳过记为通过。源码扫描确认上述依赖与计数逻辑。

## 已核实的正确部分与未验证范围

- 运行 10 数量口径本身成立：3400 候选；1842 条 h5 结果，1796 成功，1600 primary、196 spare、46 failed；720 条 reset，其中 700 交付、20 余量；838 未核验。
- 方案 B 的 210 条确为 205 成功、3 个 `DatasetGenerationError`、2 个 `EpisodeWallClockTimeout`。保留用户选定范围，不换 seed、不补成功样本。
- 固定组序、40 worker 和逐条 outcome 后，旧 reset 调度按批收齐并排序吸收结果；本轮没有把“异步完成顺序”误判成 720 条不可复现的原因。
- 未运行新链路、210 条仿真对拍、720/838 条 reset、全量 timeline 提取或全量视频解码；计划中的新模块尚未实现。本报告证明计划存在反例，不证明实施后的结果。
- RouteStick/easy/ep0 的两次同散列，只支持该输入的重复生成；210 条抽样不能排除新加载器在 episode 100 以后、其他 block 或恢复执行路径上的错误，其余 1632 条仍是未实证。
