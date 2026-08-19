# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep91/95/98/99**，每条产出 **110 帧 clip**
（env step `[34,144)` = 第一次 swap 窗口 `[64,114)` 前后各 30 帧），共 **19 条**。
机制细节、接触检测、动作泄露、十二条验收判据与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

## 数据集口径

| 性质 | 是否成立 | 证据（实测） |
| --- | --- | --- |
| ① bin 初始位置与原版 dataset 一致 | **是，逐位一致** | 同 env_seed 播种、注入零 RNG 消耗；判据 2：每条 clip 的槽位 xy 与 Phase 0 基线逐位相同；控制跑对官方 h5 的 joint_action 在 clip 区间严格 0.0；事件前 30 帧 `bins_pos` 跨变体逐位相同（差 0.0） |
| ② 第二次 swap 恒定 | **是** | 钉死为该源**原版 episode 实际发生的那次**（按槽位）：同源全部变体的第二次 swap 移动同样两个槽位，clip 末帧位置集合跨变体最大差 1.01e-6；生成闸门断言同源尾部唯一 |
| ③ 第一次 swap 排列组合不同，但受最近邻约束 | **是** | 每源枚举 2~3 个组合、彼此不同；判据 12：19/19 条的事件对都满足「其一是另一的严格最近邻」（用该源实测摆位复算，且用 clip 自身事件前一帧的位置交叉复核过） |

**源筛选**：目前只看 **4-bin** 布局（easy 是 3-bin、模板与类别体系不同，剔除），再要求
swap 次数 ≥2 且两 env 取共同源号 ⇒ **ep90-99 里只剩 {91, 95, 98, 99} 这 4 个 seed**
（Video 14100/14500/14800/14900；Button 16100/16500/16801/16900，ep98 是历史 attempt
探针值、必须读表不能公式反推）。

### 生成的排列组合

第一次 swap 的可选组合 = 每个容器配上离它最近的邻居、去重（4 容器时恒 2~3 对）。
★ = 该源原版实际发生的那对（is_original，逐位复现官方 episode）：

| 源 | 第一次 swap 的槽位组合 | 条数 |
| --- | --- | ---: |
| Video ep91 | 0-3★、1-2 | 2 |
| Video ep95 | 0-1★、0-3、1-2 | 3 |
| Video ep98 | 0-3★、1-2、2-3 | 3 |
| Video ep99 | 0-1★、0-3、2-3 | 3 |
| Button ep91 | 0-3、1-2★ | 2 |
| Button ep95 | 0-3★、1-2 | 2 |
| Button ep98 | 0-3、1-2★ | 2 |
| Button ep99 | 0-3★、1-2 | 2 |

合计 **19 条**（Video 11 + Button 8）；主标签 `event_slots` 分布 **03:8 / 12:7 / 01:2 / 23:2**。
对角组合 0-2 / 1-3 从来不是任何容器的最近邻，结构上进不了枚举——这正是旧口径 6 种全枚举
（48 条）收敛到 19 条的原因。

## 生成链路与产物

七步，每步的产物是下一步的输入；全链路（不含 Phase 0）约 1 分钟。

```
① Phase 0 控制跑  probe_original.py        8 条完整 rollout（不注入），~32 s
   └→ outputs/phase0/original_index.json   ★ 唯一不可静态重算的产物：
        · 原始 swap 序列（容器/槽位两口径）——第二次及以后钉死成什么的唯一来源
        · 原版被交换的第一个容器——「第二个 == 它的最近邻」带方向核对用
        · 容器摆位 / 各自最近邻 / 判定余量 / 合法对；布局指纹；对官方数据的红线比对
② 计划表  clip_plan.py                     纯函数，不产数据
   └→ 读①的摆位 → 逐源 2/3 条、合计 19（没有①只给 ≤48 上界，绝不冒充真值）
③ 生成    generate_swap_clips.py           19 条截断 rollout，~38 s
   └→ clips/*.h5（每变体 110 帧）  clips_manifest.json  clip_results.jsonl
      traces/ videos/ logs/
      收尾闸门：指纹与①一致、每源恰 1 条原始变体、实际换的组合 == 合法对集合
④ 合并    merge_clip_h5.py --delete-source
   └→ record_dataset_{Task}.h5             官方格式，episode 密集重编号（Video 0-10、Button 0-7）
      record_dataset_{Task}_metadata.json   seed = variant_seed
      episode_map_{Task}.json               新旧编号 ↔ 源ep/变体/标签/几何 全映射
⑤ 标签    make_clip_labels.py
   └→ clip_events.json                     ★ 主标签（主轴 event_slots + 协变量 + 约束说明）
      swap_labels_clip.json                 chunk 级二值（v7 同 schema）
      swap_events_clip.json                 chunk 级富标签
⑥ 验收    verify_clips.py                  读①④⑤三方对账
   └→ verification_report.{json,md}        十二条判据 + 告警段（退出码非 0 = 有判据未过）
⑦ 出图    draw_clip_diagrams.py
   └→ diagrams/{Task}_ep{N}_clips.png      每源一张，进不来的组合留空并标注原因
      diagrams/contact_overview.png         接触矩阵（对角两列恒空）
      diagrams/contact_timeline.png         接触落在哪些帧
```

```bash
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 8
uv run python scripts/data-generation-MotionJEPALabel/clip_plan.py --original-index scripts/data-generation-MotionJEPALabel/outputs/phase0/original_index.json
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_clips.py --output-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --gpus 0,1 --workers 16
uv run python scripts/data-generation-MotionJEPALabel/merge_clip_h5.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --delete-source
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --regression   # 改判正规则后必跑，319/319
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/verify_clips.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/draw_clip_diagrams.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

两条硬顺序约束：**①必须早于删除任何旧产物**（第二次及以后 swap 换的是谁只能实跑读回，
静态算不出）；**③④⑤必须同批**（④删源，源没了无法只重跑④）。
磁盘：`outputs/phase0/` 2.1 GiB（索引产出后 h5/录像可删、索引要留）+ `outputs/event1/` 1.4 GiB，均已 gitignore。
