# PatternLock-01 独立复核记录（AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1）

## 1. 源码核对（git show AUDIT_BASE:src/robomme/robomme_env/PatternLock.py）
- config_xhard4 的注释块（紧邻其上）原文：
  "V4 xhard（派生自 hard，B8）：布局与搜法都不动，只把节点数提到 [20,24]。
   V5（计划 2.10，L35/L36）：节点数固定 25（5×5 不重访路径的上限）。规划期探针 P3 发现按 [24,25]
   搜到第一条在区间内的路径就停时 86% 的局只有 24 节点，故实施方收成 [25,25]；配合 xhard 搜索预算
   20000（decision.xhard.path_search_max_attempts）与耗尽抛真 SceneGenerationError，杜绝静默用错长路径。"
  紧接其下：config_xhard4 = {"grid": 5, "length": [21, 25]}
  → 确认 finding 对注释原文与实际取值的引用准确无误；注释虽标注"V5"字样，但直接压在
    [21,25] 的当前取值上方，且 V6 引入 xhard1-3 的段落未回头说明 xhard4 从 V5 的
    [25,25] 改回 [21,25] 的缘由——这段历史叙述在阅读顺序上确实容易被误读为当前行为。
- XHARD_DECISION 注释"20000 次下 25 节点命中率实测 1.000"同样只针对 V5 语境，
  与当前 [21,25] 取值域无必然对应关系，但仍原样保留在当前代码路径可达的模块级注释里。
- _load_scene 循环：`if length_range[0] <= len(path_nodes) <= length_range[1]: break`
  （DFS 找到第一条落在区间内的路径就停）→ 与注释描述的算法机制一致，是导致长度分布
  偏向下界的直接原因，机制层面无误。
- native 三档（config_easy/hard/medium）源码只有纯字典，无此类历史演进叙述性注释
  → native 对照成立，问题仅见于 xhard4（新档专属）。

## 2. 数据独立复核（不复用 finding 自带数字，重新从 specs.jsonl 计算）
命令：`python3` 直接解析 `artifacts/newtask-v6/v6-01/xhard4/specs.jsonl` 全部 10 条 PatternLock attempt=0 记录，
逐条统计 `len(spec.actions.path_nodes)` 与 `spec.actions.path_attempts`：

```
ep0 selected=True  len=21 attempts=6
ep1 selected=False len=21 attempts=27
ep2 selected=False len=22 attempts=32
ep3 selected=True  len=21 attempts=31
ep4 selected=False len=21 attempts=54
ep5 selected=False len=21 attempts=10
ep6 selected=True  len=23 attempts=2
ep7 selected=False len=21 attempts=67
ep8 selected=False len=23 attempts=30
ep9 selected=False len=22 attempts=16

Counter({21: 6, 22: 2, 23: 2})   # 与 finding 的 {21:6,22:2,23:2} 完全一致
mean(attempts) = 27.5            # 与 finding 一致
max(len) = 23                    # 0/10 达到 24 或 25，与 finding 一致
selected(ep0/3/6) lens = 21/21/23  # 与 finding 完全一致
```
→ 独立复算结果与 finding 所列数字逐位吻合，非复制粘贴 finding 自身数字。

## 3. 计划对照
`git show AUDIT_BASE:0925-newtask-release-v6-plan.md` §三表格第 10 行（PatternLock）：
xhard4 列值为 "[21,25]"，与源码 config_xhard4 完全一致 → **配置值本身与计划无出入**，
问题纯粹是"过期注释叙事"与"分布偏下界"两点，不是配置值偏离计划。

## 4. 排重核对
排查 `artifacts/audit/v6-semantic-evidence-01a0e086/审查汇总.md` 的既知 D4 条目：
D4 = "PatternLock/hard 展示搜索预算 20000，实际原 hard 仍 1000"——针对的是 hard 档
搜索预算展示文案问题，与本 finding（xhard4 节点数注释过期 + 实际分布不达上界）
主题、锚点均不同，不构成重复。

## 结论
- CONFIRMED：注释原文引用准确、实际配置值引用准确、10 条 spec 的节点数分布与
  attempts 均值独立复算后逐位吻合，DFS "找到第一条即停" 机制解释了分布偏下界的成因，
  native 三档无此类注释问题。
- category=new_tier_only 成立：问题只存在于 xhard4 专属的历史演进注释与其驱动的分布
  特性中，native 无对应问题；配置值本身与 V6 计划完全一致，不构成 native_vs_new_mismatch
  （因为有明确计划依据 [21,25]）。
- 不需要新仿真：全部证据均可从 AUDIT_BASE 源码 + 已交付的 specs.jsonl 静态复核，
  10/10 episode 的 spec 记录已完整覆盖节点数分布问题，无需补跑。
