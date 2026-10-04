测试重构设计的现状验证（2026-10-03）

本轮确认现有测试覆盖不完整，且有六个CPU可复现的漏检。这里是计划依据，不是重构完成报告。方案见 [测试重构计划](../../plans/1003-benchmark-tests-refactor-plan.md)，原维护文档见 [第四节](../../../1003-code-test-maintenance-todo.md)。

## 固定对象、范围与环境

`BASE=86e5a015b7ba3a85c2c03cc50f5de482b9476c1d`，分支 `newtaskRelease-taskV9`，sled-vail，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`；uv管理现有`.venv`，只用 `uv run --frozen --no-sync`，没有安装或同步依赖。机器有2张RTX6000 Ada，但本轮不创建真实环境、不执行reset/轨迹/模型，也没有提交集群作业。

9个子代理按测试盘点、原生语义、hard适配、生成、评估、对拍噪声、记录数据、站点/交付、独立架构分别只读固定Git对象，另对新文档进行了交叉复核。主会话执行CPU探针。静态候选与实测复现分开，没有用静态结论填动态PASS。

开工排除的在途内容为 `third_party/SimpleMemVLA`、`docs/validation/newtask-v9/hf-20261003.md`、`docs/validation/newtask-v9/hf-20261003/`；没有提交、清理或覆盖它们。实测前用以下命令核测试及被测源码与BASE一致，退出0：

```bash
git diff --quiet 86e5a015b7ba3a85c2c03cc50f5de482b9476c1d -- src scripts tests pyproject.toml uv.lock
```

统计来自固定Git对象和AST：109个test文件（lightweight102、dataset7）、1106个test_函数定义；不是pytest参数化收集总数。生产Python为robomme54、hard62、scripts71、challenge9，共196文件，快照见 [inventory-summary.json](records/inventory-summary.json)。全库还有shell/HTML/JSON等责任，尚未做正式branch覆盖采集；本轮预检时未安装coverage/pytest_cov，没有为本轮安装它们。

收官时HEAD已由BASE变为 `8865220627f25536498f0daa9f20f386b09c6c4f`，其他会话提交HF留档、另一份测试设计/运行记录及待定清单等文档；本文仍锚定BASE，不把后续59格reset或coverage记录并作本轮证据。再次核对 `src/scripts/tests/challenge_interface/pyproject.toml/uv.lock` 与BASE无差异；其他会话提交保留。

## 实测结果

| 探针 | 结果 | 退出码 | 小证据 |
|---|---|---|---|
| CPU最小选集4文件 | 29 passed，0.82s | 0 | [smoke.log](records/smoke.log)、[smoke.xml](records/smoke.xml) |
| CPU契约选集7文件 | 192 passed，9.12s | 0 | [contracts.log](records/contracts.log)、[contracts.xml](records/contracts.xml) |
| 旧语言/错误处理2文件 | 27 passed、4 failed，1.01s | 1 | [known.log](records/known.log)、[known.xml](records/known.xml) |
| main-only3文件收集 | no tests collected，0.17s | 5 | [discovery.log](records/discovery.log) |
| 类型与空H5反例 | 四项均被当前实现接受 | 0（诊断成功，不表示实现正确） | [counterexamples.json](records/counterexamples.json) |
| 空冻结文件与根属性反例 | 两项均复现漏检 | 0（诊断成功） | [additional-counterexamples.json](records/additional-counterexamples.json) |

具名结果：`CPU_SMOKE=PASS passed=29 pytest_s=0.82 exit=0`；`CPU_CONTRACT_SUBSET=PASS passed=192 pytest_s=9.12 exit=0`；`KNOWN_FAILURE_PROBE=FAIL failed=4 passed=27 exit=1`；`TEST_DISCOVERY_PROBE=FAIL empty_files=3 collected=0 exit=5`；`COUNTEREXAMPLES=CONFIRMED cases=6`。

资源使用结论来自已核对的调用范围：未调用gym.make/scene创建/真实reset/规划/模型。本轮没有安装用于未来验收的资源守卫，因此没有声称已获得 `TEST_RESOURCE=PASS` 的运行时仪器证据。反例JSON里的零调用字段是该探针的范围声明，不是GPU监控采样。

四个旧失败分别为未知环境目标期待 `[""]`而实为`[]`；Swing文案连接符不符；错误处理AST期待try块；replay脚本状态扫描与官方现状不符。不能把这四项全部归为生产错误，也不能只改断言就宣称异常处理符合文档。

## 可复现的pytest命令

以下均在仓库根执行。每次替换为全新诊断目录，核父目录是本工作副本artifacts实体路径；`--basetemp`不能复用或指向symlink。日志以pipefail＋tee落盘，退出码看记录的原始pytest状态。下面省略tee只展示核心命令；本轮原始日志已保留。

```bash
export UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/.cache/uv
export CUDA_VISIBLE_DEVICES=''

timeout 120s uv run --frozen --no-sync python -m pytest \
  tests/lightweight/test_h5_parity_compare.py \
  tests/lightweight/test_scripts_do_not_import_tests.py \
  tests/lightweight/test_seed_layout.py \
  tests/lightweight/test_env_digest_compare.py \
  -q --durations=12 --basetemp=artifacts/<新诊断名>/tmp-smoke \
  -o cache_dir=artifacts/<新诊断名>/pytest-cache \
  --junitxml=artifacts/<新诊断名>/smoke.xml

timeout 160s uv run --frozen --no-sync python -m pytest \
  tests/lightweight/test_noise_gate.py \
  tests/lightweight/test_v8_specs_schema.py \
  tests/lightweight/test_v9_packaged_800.py \
  tests/lightweight/test_v9_subset_specs.py \
  tests/lightweight/test_hard_builder_xhard0.py \
  tests/lightweight/test_v8_eval_manifest.py \
  tests/lightweight/test_v8_eval_report.py \
  -q --durations=15 --basetemp=artifacts/<新诊断名>/tmp-contracts \
  -o cache_dir=artifacts/<新诊断名>/pytest-cache \
  --junitxml=artifacts/<新诊断名>/contracts.xml

timeout 60s uv run --frozen --no-sync python -m pytest \
  tests/lightweight/test_TaskGoal.py tests/lightweight/test_step_error_handling.py \
  -q --basetemp=artifacts/<新诊断名>/tmp-known \
  -o cache_dir=artifacts/<新诊断名>/pytest-cache \
  --junitxml=artifacts/<新诊断名>/known.xml

timeout 30s uv run --frozen --no-sync python -m pytest \
  tests/lightweight/test_record_info_is_completed.py \
  tests/lightweight/test_record_waypoint_pending_flow.py \
  tests/lightweight/test_waypoint_dense_dedup.py --collect-only -q \
  -o cache_dir=artifacts/<新诊断名>/pytest-cache
```

本轮不执行tests/dataset全集：其生成夹具最多30次换seed、修改规划器，超出此次初始/reset边界。也不裸pytest扫描第三方和历史留档。

## 六个反例的完整调用

以下诊断在全新artifacts临时目录写微型坏输入，调用当前真实生产函数，不修改生产源码、规格或正式数据。Python片段用 `uv run --frozen --no-sync python -` 执行；`probe_root`替换成新目录，执行前确认BASE和环境。

```python
from pathlib import Path
import runpy
import h5py
from scripts.parity import noise_gate as ng, gate_set

probe_root = Path("artifacts/<新诊断名>/counterexamples")
probe_root.mkdir(parents=True, exist_ok=False)

# 1：空H5真实sha相同，得到byte_equal，尚不能代表有效产物。
a, b = probe_root / "a.h5", probe_root / "b.h5"
a.write_bytes(b"")
b.write_bytes(b"")
identity = {"id": "BinFill|xhard1|16400000", "task": "BinFill", "tier": "xhard1", "seed": 16400000}
def entry(path):
    return {"h5": str(path), "sha256": None, "status": "ok", "tier": "xhard1"}
print(ng.classify_pair(identity, entry(a), entry(b))["class"])

# 2～4：独立规格builder构造合法两行，每次改一字段后重签。
schema = runpy.run_path("tests/lightweight/test_v8_specs_schema.py")
for field, index, value in [("candidate", 1, True), ("attempt", 0, 0.5), ("seed", 0, "float")]:
    header, rows = schema["build_tier"]("xhard5", {"StopCube": 2}, spare=0)
    rows[index][field] = float(rows[index][field]) if value == "float" else value
    header = schema["_resign"](header, rows)
    schema["H"].validate_specs(header, rows)
    print(field, "accepted", rows[index][field])

# 5：已存在但零字节冻结文件，实际调用check仍得到PASS。
empty_gate = probe_root / "empty-gate.json"
empty_gate.write_bytes(b"")
print(gate_set.check(empty_gate))

# 6：两份真实微型H5仅改根属性，sha不同但字段差异仍0。
pair = runpy.run_path("tests/lightweight/test_h5_parity_compare.py")
left = pair["_write"](probe_root / "root-left.h5")
right = pair["_write"](probe_root / "root-right.h5")
with h5py.File(right, "a") as handle:
    handle.attrs["source_identity"] = "wrong-source"
result = pair["parity"].compare_h5_pair(left, right)
print(result["sha_equal"], result["field_mismatch"])
```

空冻结探针输出的交付检查规模是V9的43个有效任务档格×3个身份=129；它只是CPU规格读取，没有生成或reset。这个探针表明缺失冻结内容被自身重算结果替代，而非这129个身份本身有误。

## 未验证范围与后续

未运行全套旧测试、coverage、完整源码变异、真实wrapper写读集成、HTTP/浏览器、独立wheel安装、challenge协议、模型与物理闭环。静态发现的录制视频关闭问题、恢复重复执行、成功状态误计分等仍是待实测候选。

下一步依据计划建立默认资源与契约执行框架，再按域重写测试。本轮生产实现和测试均未修改，六项漏检没有修复；不能把计划完成称作测试重构完成。

原始临时产物保存在 `artifacts/test-reconstruction-20261003-01/`；records只存小日志、XML和反例JSON，不存轨迹、权重、venv、源码快照或配置脚本拷贝。归档known.xml与known.log仅去掉错误文本的行尾空白以通过diff检查，用例/失败/skip结构不变；原始XML与日志仍在artifacts。
