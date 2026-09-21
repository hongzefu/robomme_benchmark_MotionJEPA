# 全环境原值方案对抗审查

结论：**当前方案未通过对抗验证，确认三项 P1 阻断和一项 P2 规格完整性缺口。** 两项来自144条子集与旧验收接口不兼容，一项来自历史报告无法投影数值统计，另一项是xy失败恢复的实际随机输入没有进入明确的规格消费清单。

用户原话：「/data/hongzefu/robomme\_benchmark\_MotionJEPANewTask/NEWTASK\_RELEASE\_V3\_PLAN.md」「对抗验证」。本轮只审查，不实施方案，不修改原方案、生产代码或配置，不启动仿真、不生成新轨迹。

审查对象为 `newtask-v2.1refractor@74dc5ce7224fe5b95319897332747d538395ec29`（11.28）的 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md)。原文件 SHA-256 为 `78faf72d69be6fda79f7cd84df3c08288666d9a96d1a1c4e68cc729196690bf8`。官方依据为本地可读的固定 Git 对象 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`，不以移动分支代替；全部反例读取该对象中的源码或metadata。工作区初始干净。

## 一、P7仍验96条恢复，但144条子集实际只有80条（P1）

方案第一部分第四节「抽样规模」要求每环境每难度按官方metadata顺序取前三条；若缺z、xy或关闭模式才替换。固定官方十六环境的结果完全相同：

| 难度 | 选中的原episode | 恢复模式 |
| --- | --- | --- |
| easy | 0、1、4 | z、z、xy |
| medium | 2、6、10 | z、关闭、关闭 |
| hard | 3、7、11 | xy、关闭、关闭 |

依据官方 `scripts/data-generation/generate_dataset.py::EpisodeJob.recovery_mode`，全子集为 **z=48、xy=32、关闭=64，共80条配置恢复**。三种模式已齐全，方案的替换分支不会触发。判据P7仍要求 `RECOVERY_PARITY=PASS configured=96`，这个96属于1600条全集，不能作为实际只执行144条的恢复覆盖数。

第二部分9.3还保留每环境episode 0～5全部纳入的要求，但其中easy有0、1、4、5四条，与每格3条不能并存。第二部分已声明以第一部分为准，因此这里不另算一项缺陷；需要随P7一起清除旧范围的歧义。

建议保持用户要求的144条，P7从冻结manifest计算 `configured=80,z=48,xy=32,off=64`，明确每环境episode 5未验证；全集的96仅作为来源统计。不能用1600条配置清单的计数冒充144条的运行事件覆盖。

## 二、步骤5e指定的原比较器拒绝该稀疏子集（P1）

方案R1、步骤5e及第二部分逐文件清单要求调用固定官方合同和动作比较器。两个原函数实际都有前置守卫：

```python
episode_indices != list(range(len(episode_indices)))
```

锚点为固定官方 `scripts/data-generation/validate_generated_dataset_contract.py::validate_generated_dataset_contract` 和 `scripts/data-generation/compare_joint_actions.py::compare_joint_actions`。将真实子集 `[0,1,2,3,4,6,7,10,11]` 传入未改动的函数，尚未读取任何HDF5便分别抛出：

```text
DatasetContractError: validation episodes must be a contiguous range starting at 0
JointActionComparisonError: comparison episodes must be a contiguous range starting at 0
```

原CLI的 `--episodes 9` 也不能代替该子集：它选择0～8，漏掉10、11，同时额外要求5、8。身份不重算、只跑144条、直接使用原比较器这三条目前不能同时成立。

建议在方案里明确：保留原字段与数值比较核心，为冻结manifest的任意原episode集合适配范围校验，并用连续全集回归和稀疏反例验证适配器；官方原文件保持冻结。不能重编号episode、伪造缺失HDF5或扩大到1600条来绕过用户范围。

## 三、历史动作差异只有全集摘要，不能投影为144条的R1（P1）

即使修复第二项，R1的 `compared=144 detail_mismatch=0` 仍有证据缺口。方案步骤5e及9.5「对照分三项」要求对照历史逐条结果、失败位置和数值摘要，但固定报告 `scripts/data-generation/reports/generation_report.json::validation.joint_action_comparison` 仅有全1600条的数值总计、一个最大差位置及错误列表，没有逐episode动作差异统计。

实测历史217242个非零差异元素不能拆出属于144条的部分；唯一最大差位于 **BinFill/episode_99/timestep_625/element_index=5**，不在子集。十条历史时间步错误只有 **BinFill/episode_11、PickHighlight/episode_3** 在子集中，不能要求子集复现全集的10条错误。

`generation.results` 及合同审计的逐局记录可以投影身份、恢复模式、成功和帧数；动作数值全局摘要不能投影。这不是重跑发布参考集就能补齐的历史证据：新运行能产生新的逐局摘要，不能反推旧1600条中每条的贡献。方案已正确标记历史HDF5缺失，但尚未将这个缺失传播到R1的可判定范围。

建议把R1拆开：历史逐条可读字段按144条对照；本次144条对发布参考集的动作比较作为新结果留档；历史子集动作数值漂移核验在找回原成品或逐局旧摘要前记为不可比。不能把不可比的历史数值摘要计作匹配，并据此给出未拆分的R1整体通过；可投影字段单独报告 `detail_mismatch=0` 时须明确字段范围。A1／A2／B／C／D的本次逐位对拍仍可独立完成，历史全集失败原文继续保留。

## 四、恢复规格漏列xy扰动的实际消费点（P2）

方案第二节各环境的 `episode_spec.actions.recovery`、第二部分8.1的 `actions` 和逐文件清单主要描述失败动作索引、模式及选择；尚未明确列出执行时的xy方向及偏移消费。官方和当前源码都存在另一条独立随机链：

```text
subgoal_planner_func.py::_get_fail_recover_rng
  → 按env.seed建立独立Torch generator
_sample_fail_recover_xy_signs
  → randint(-1,2,(2,),dtype=int64)，拒绝[0,0]
solve_pickup_fail
  → signs.astype(float32) × xy_offset
  → signed_offset实际加到fail_pose_p的x、y
```

真实官方身份中，`VideoPlaceOrder/episode_4/seed11401` 抽 `[0,0]` 后重抽 `[-1,-1]`；`VideoUnmaskSwap/episode_3/seed5300` 抽 `[0,0]` 后重抽 `[-1,0]`。两者都位于144条子集中。这发生在求解执行阶段，与 `task4recovery.py::inject_fail_grasp` 选择哪个动作是不同的随机事件。

对官方BinFill/episode_3的seed4301进行纯CPU反例：C得到 `[1,-1]`，错误D完全不读取外部规格，继续调用原函数，也得到 `[1,-1]`，随机流最终状态相同。**输出相等和随机流相等不足以证明恢复方向来自外部规格。** 本反例没有运行HDF5生成，也不声称已执行未来D链路；它证明此处必须有独立的赋值消费验收。

方案G4要求“绕开规格赋值必须被发现”方向正确，但其预期字段清单必须包含这个消费点，才能判定missing或unused。`sampling_trace`泛指全部源只解决记录和核验，不自动建立外部方向驱动抓取位置的关系。

建议显式补入恢复事件编号、独立随机源、`xy_signs`、拒绝重抽、派生 `signed_offset` 与实际 `fail_pose_p` 绑定；D中由冻结符号驱动偏移，原RNG只兼容核验，派生偏移不设第二套独立真值。将上述公共工具函数列为逐项审批候选，并为其增加“保持重抽但绕过规格”的G4反例。此项是冻结原有行为，不是新增恢复分布；本轮没有改动或覆盖这些函数。

## 五、可复制的隔离反例

以下命令在仓库根目录执行。第一段只读Git对象，AST只提取原异常类及函数，在读取数据前触发原参数守卫；第二段只提取原CPU抽样函数，未导入或覆盖生产环境模块。两段都退出0；这里的PASS表示成功复现反例，不表示方案通过。

### 5.1 子集计数、比较器拒绝及报告范围

```bash
command -v uv && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python - <<'PY'
import ast
from collections import Counter
from pathlib import Path
import json
import subprocess

ref = 'd53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa'
def blob(path):
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'], text=True)

paths = subprocess.check_output([
    'git', 'ls-tree', '-r', '--name-only', ref,
    'src/robomme/env_metadata/train'
], text=True).splitlines()
selected = []
for path in paths:
    if not path.endswith('.json'):
        continue
    records = json.loads(blob(path))['records']
    chosen = sum(([r for r in records if r['difficulty'] == d][:3]
                  for d in ('easy', 'medium', 'hard')), [])
    assert sorted(r['episode'] for r in chosen) == [0,1,2,3,4,6,7,10,11]
    selected.extend(chosen)
modes = Counter('z' if r['episode'] <= 2 else 'xy' if r['episode'] <= 5
                else 'off' for r in selected)
assert len(selected) == 144 and modes == Counter(z=48, xy=32, off=64)
print('SUBSET rows=144 z=48 xy=32 off=64 configured=80')

episodes = [0,1,2,3,4,6,7,10,11]
cases = (
    ('validate_generated_dataset_contract.py', 'DatasetContractError',
     'validate_generated_dataset_contract',
     ('artifacts/no-audit-io', ['BinFill'], episodes)),
    ('compare_joint_actions.py', 'JointActionComparisonError',
     'compare_joint_actions',
     ('artifacts/no-audit-io', 'data/robomme_data_h5', ['BinFill'], episodes)),
)
for filename, error_class, function, args in cases:
    tree = ast.parse(blob('scripts/data-generation/' + filename))
    nodes = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in (error_class, function)]
    future = ast.ImportFrom(module='__future__',
                            names=[ast.alias(name='annotations')], level=0)
    module = ast.fix_missing_locations(
        ast.Module(body=[future, *nodes], type_ignores=[]))
    scope = {'Path': Path, 'REFERENCE_ROOT': Path('data/robomme_data_h5'),
             'METADATA_ROOT': Path('src/robomme/env_metadata/train'),
             'ALL_TASKS': ['BinFill']}
    exec(compile(module, filename, 'exec'), scope)
    try:
        scope[function](*args)
    except scope[error_class] as exc:
        assert 'contiguous range starting at 0' in str(exc)
        print('OFFICIAL_REJECT', function, str(exc))
    else:
        raise AssertionError('预期原函数拒绝非连续子集')

report = json.loads(blob('scripts/data-generation/reports/generation_report.json'))
comparison = report['validation']['joint_action_comparison']
location = comparison['max_abs_diff_location']
keys = {(r['task'], r['episode']) for r in selected}
print('REPORT_SCOPE', len(keys), 'global_max_in_subset',
      (location['task'], location['episode']) in keys)
print('REPORT_NUMERIC_FIELDS', list(comparison))
print('REPORT_NUMERIC_EPISODE_ARRAYS', [k for k, v in comparison.items()
      if isinstance(v, list) and k != 'errors'])
print('REPORT_MAX_LOCATION', location)
print('REPORT_SUBSET_TIMESTEP_ERRORS', [error for error in comparison['errors']
      if (error.split('/')[0], int(error.split('/episode_')[1].split(':')[0]))
      in keys])
print('ADVERSARIAL_CHECK=PASS metadata=16 identities=144 rejected_comparators=2')
PY
```

实测关键结果为 `configured=80`、两个 `OFFICIAL_REJECT`、`global_max_in_subset False`、`REPORT_NUMERIC_EPISODE_ARRAYS []`，子集历史时间步错误为上述两条；退出0。

### 5.2 xy恢复的独立随机源与绕过规格反例

```bash
command -v uv && PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python - <<'PY'
import ast
import subprocess
from types import SimpleNamespace
import numpy as np
import torch

source = subprocess.check_output([
    'git', 'show',
    'd53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa:src/robomme/robomme_env/utils/subgoal_planner_func.py'
], text=True)
names = {'_coerce_seed_to_int', '_get_fail_recover_rng',
         '_sample_fail_recover_xy_signs'}
node = ast.Module(body=[n for n in ast.parse(source).body
    if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
assert len(node.body) == 3
scope = {'np': np, 'torch': torch}
exec(compile(node, '<官方纯抽样函数>', 'exec'), scope)
sample = scope['_sample_fail_recover_xy_signs']

for seed in [11401, 5300]:
    generator = torch.Generator().manual_seed(seed)
    raw = []
    while not raw or raw[-1] == [0, 0]:
        raw.append(torch.randint(-1, 2, (2,), generator=generator,
                                 dtype=torch.int64).tolist())
    accepted, _ = sample(SimpleNamespace(seed=seed))
    print('RECOVERY_REJECTION', seed, raw, accepted.tolist())

class ReadCount(dict):
    reads = 0
    def __getitem__(self, key):
        self.reads += 1
        return super().__getitem__(key)

c, d = SimpleNamespace(seed=4301), SimpleNamespace(seed=4301)
c_signs, _ = sample(c)
spec = ReadCount(xy_signs=c_signs.tolist())
# 故意绕过外部规格，直接重抽；输出和随机流状态仍然相同。
d_signs, _ = sample(d)
output_equal = bool(np.array_equal(c_signs, d_signs))
state_equal = torch.equal(c._fail_recover_rng.get_state(),
                         d._fail_recover_rng.get_state())
assert output_equal and state_equal and spec.reads == 0
print('SPEC_BYPASS output_equal=%s state_equal=%s spec_signs_reads=%d'
      % (output_equal, state_equal, spec.reads))
PY
```

实测重抽序列为 `11401: [[0,0],[-1,-1]]`、`5300: [[0,0],[-1,0]]`；seed4301的双方符号均为 `[1,-1]`，`output_equal=True state_equal=True spec_signs_reads=0`；退出0。

## 六、已有测试、核验边界与留档

现有配置和比较器反例回归：

```bash
command -v uv
timeout 280s uv run --no-sync python -m pytest \
  tests/lightweight/test_native_sampling_config.py \
  tests/lightweight/test_native_sampling_evidence.py -q \
  --basetemp artifacts/train-parity/20260921-plan-audit/pytest-tmp
```

结果 **62 passed，3.05秒，退出0**。原始输出保存于 `artifacts/train-parity/20260921-plan-audit/pytest.log`，尾行 `EXIT_CODE=0`；测试临时产物都在同一仓库内目录。这些是现有工具的回归，不覆盖待实施的十六环境接口与本报告四项问题。没有运行全套测试或真实五路生成。

已核对冻结录像器与官方d53字节相同。A路恢复事件的脚本侧只读取证机制尚须在实施前具体化；因可通过只读观测补充，本轮不把它另列为已证实阻断。单条跨卡测试不能外推所有任务，但方案后续还有子集多worker与两卡核验，本轮没有证据另报GPU数值缺陷。未实施的脚本和配置已明确标为待新增，不因文件尚不存在而报错。

修订建议只作用于后续方案，不构成本轮实施授权。原方案与生产文件保持不变；本轮仅提交本报告和AGENTS账本，不推送、不切分支。
