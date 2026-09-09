# 对象与动作冻结：完整五项对拍

状态：保留的中间验证，不能作为最终五项通过报告。运行编号为 `20260909-actions-v2`。

60/60 次 fresh 生成、15 格四对原观察器证据及 HDF5 比较均通过；852 张图版已在本轮
实际逐张查看。但收尾复核发现观察器只记录抽样后 generator 状态，未完整记录调用前
与全局 Torch 状态，不满足本轮第④项。已停止后续编排并保留全部产物，修订为观察器
版本 3 后另以独立编号重跑。本轮目视记录只有在最终新图与已看图逐项散列一致时才可
绑定，否则必须重新查看；不能仅凭路径或旧比较结论沿用。

## 实现与固定输入

产品代码提交 `c56e5af`（10.8），观察器和完整验证驱动提交 `f8eb08c`（10.9），
逐图目视工具提交 `12c170e`（10.10）。原基线固定为
`94449db0a068a6b454b55a13ebd48f0394d89cc8`，原入口在仓库内 detached worktree。

- `uv.lock` SHA-256：`983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`。
- `pyproject.toml` SHA-256：`bc2346e4526c2b5c2177fe5191710c81f883c21017d45928e615327cf29cb21a`。
- schema 3 配置 SHA-256：`8fae52b7cf20bfcdb71b0a8d6378924e423a0e66450d3d51f95e9a66aeccd2bc`。
- 沿用原 15 格 cases.json，每格 A1/A2/B/C 独立运行，GPU 0、单 worker、单 episode、attempt 0。
- 新增配置固定对象选择与路线规则，具体对象及动作由原 episode seed 和运行状态确定；不新增逐 episode 结果表。

## 当前证据

短测 106 项通过；新版观察器四路单格生成成功，共 117.3 秒；四对 HDF5、状态、事件、
随机流、记录映射及 reset RGB 一致，原版启用/关闭观察器的 HDF5 差异 0。

正式矩阵 60/60 次 fresh 生成成功，共 2439.0 秒；15 格四对原观察器字段与 HDF5
比较通过，30 次原版运行的 RRT* 回退均为零。852 张图版全部逐图查看，包含 837 张
HDF5 关键帧与 15 张 reset。后续合并、隔离和补充回归未在本运行完成。
由于随机状态记录缺口，本运行不构成完整五项验收；最终使用
[20260909-actions-v3](../20260909-actions-v3/README.md) 的独立证据。

## 当时的执行入口

以下记录当时使用的命令。当前代码重新生成须使用新的运行编号，按最终报告执行，
不能向本目录继续混入不同观察器版本的证据。完整日志保留在
`artifacts/logs/action-freeze-v2.log`，中止时没有成功退出标记。

```bash
uv run --no-sync python -m tests._shared.parity_runner --run-id 20260909-actions-v2
uv run --no-sync python -m tests._shared.action_freeze_campaign --run-id 20260909-actions-v2
```

目视可以逐格提前进行，但 collect 会先核对该格四路完整比较：

```bash
uv run --no-sync python -m tests._shared.parity_review collect \
  --run-id 20260909-actions-v2 --cell BinFill-easy-dynamicTrue
```

原尺寸画板仅将 A1/B/C 的双相机原图区排列，不缩放；差分列及像素统计保留在原图版。
实际查看后用 mark 绑定画板和原图版散列，准备画板不代表目视通过。

## 本轮处理的验证缺口

旧关键帧工具未实际接入事件 extra，且环境步不能直接当 HDF5 的 buffer 连续编号。
观察器现在记录 wrapper.step 的真实事件区间和 buffer 追加区间，事件按该映射选帧，
没有记录的事件明确列出；原 reset RGB 另行无损转存和出图，不额外渲染。
连续 worker 同时核对父进程和实际池进程内每局前后的类配置散列。

初次运行 `20260909-actions-c56e5af` 在发现上述验证缺口后中止，所有中间产物保留，
不与本次 fresh 证据混合。旧历史报告和目视结论也不直接沿用。
