# 阶段零结果

阶段零闸门通过。三十个母 seed 中，口径 B 通过二十七个，剔除三个，未超过用户规定的六个停止上限。完整按钮包络与只用按钮底座的 G 在三十个 seed 上均相同。尚未实施 W2，尚未验证真实交换轨迹，不据此宣称生成成功。

## 版本、命令与退出状态

预扫从干净提交 `adefbe3e94b5fb2acfe78ec7ba69cf5611c74207` 启动，命令见 [启动档案](launch.md)，实际会话 `xh-swapv2-scan-1012`，日志 `artifacts/logs/xh-swapv2-scan-1012.log`。仅三十 seed 的 reset，无 rollout，无换 seed 或重试。`EXIT_CODE=0`，完整 JSON 与日志保存在 `records/graph_scan.json`、`records/graph_scan.txt`。

## 实测判定

- `FREEZE=PASS files=426`，冻结日志退出零，旧目录全部只读。
- `OLD_RUN_READONLY=PASS files=426`，逐文件及目录权限核验通过。
- `BUTTON_ENVELOPE=PASS buttons=3 base_box=1 cap_cylinder=1 cap_inside_base=1`。
- `SWAP_V2_GRAPH_SCAN=INFO seeds=30 b_pass=27 b_reject=3 base_envelope_diff=0`。
- `GRAPH_SCAN_GATE=PASS b_reject=3 limit=6`。

| 官网编号 | 任务 | 通过 / 总数 | 剔除 seed | 孤立槽 |
|---|---|---|---|---|
| 2.3 | VideoUnmaskSwap | 10 / 10 | 无 | 无 |
| 2.4 | ButtonUnmaskSwap | 9 / 10 | 10500 | 3 |
| 3.2 | VideoRepick | 8 / 10 | 10000、10400 | 均为 0 |

包络相对底座结果相同仅覆盖本次三十种布局，不代表任意布局中二者等价。三个剔除 seed 不补、不换；真实运行期仍须逐段重证、槽位绑定、端点及子步检查。

## W1 合并前材料

W1 工作树基线 `a00efbe1c00569934f12f4dd398d2a8b0e20e118`，分支 `codex/swapv2-w1`。三个提交为 `ff19c957cde4cda1d79b9806ae25935e491ecfa4`、`7f7748288ba654650516ccd9ec70432c5e436ad7`、`abfa4110a348a9985efb91aa27e351504beeb9eb`。主会话复核 `REVERT_V1=PASS paths=2 diff=0 removed=10`、`SRC_ROBOMME_ZERO_DIFF=PASS base=0ec9951b`，两份引入源码完整 SHA256 与计划一致。代理测试证据 `VENDOR_TESTS=PASS tests=36 exit=0 seconds=3.67`，日志已归档。

独立审查 `PRE_MERGE_REVIEW=PASS`，锚点为上述基线至 W1 最后提交。审查确认撤回范围、十个恢复文件、两份引入文件、来源文档及测试符合计划，受保护目录零差异，子提交父链完整。审查未运行测试。W1 临时没有 `swap_plan.py` 属于计划中间状态，W2 合入前不运行生成。

## 事件与边界

归档 `.log` 被仓库全局忽略，因此原始日志改以 `.txt` 留档，没有改变日志内容或忽略配置。没有机制、接口、失败处理、预算与验收口径调整。下一步按批准计划合并 W1、核心短测，再派 W2。
