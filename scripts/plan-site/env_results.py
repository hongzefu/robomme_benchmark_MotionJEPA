"""统一环境页：冻结实测快照、历史梯度表解析与严格媒体白名单。"""
from __future__ import annotations

import html
import json
import pathlib
import re

TASKS = ["BinFill", "PickXtimes", "SwingXtimes", "StopCube", "VideoUnmask", "ButtonUnmask",
         "VideoUnmaskSwap", "ButtonUnmaskSwap", "PickHighlight", "VideoRepick", "VideoPlaceButton",
         "VideoPlaceOrder", "MoveCube", "InsertPeg", "PatternLock", "RouteStick"]
LEVELS = ["mother", "xhard12", "xhard14", "xhard16", "xhard18", "xhard20"]
SELECTED = {"VideoUnmaskSwap": [5700, 6100, 6900], "ButtonUnmaskSwap": [7700, 8100, 8900],
            "VideoRepick": [9600, 11200, 11602]}
GROUPS = [("counting", "计数"), ("permanence", "永久性"), ("reference", "参考"), ("imitation", "模仿")]
SOURCE_BASE = "https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/a43fa09c94317356091db6ba634a8f167b84ca13/"


def plain(value):
    # 标签是文本边界，不能把旋钮末尾数字与下一行长度拼成新数字。
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def expected_from_plan(doc):
    match = re.search(r'<table id="length-gradient-table">(.*?)</table>', doc, re.S)
    if not match:
        raise ValueError("缺少 length-gradient-table")
    result = {}
    for task, body in re.findall(r'<tr data-task="([^"]+)">(.*?)</tr>', match[1], re.S):
        cells = re.findall(r'<td\b([^>]*)>(.*?)</td>', body, re.S)
        if len(cells) != 9:
            raise ValueError(f"历史梯度列数错误：{task}")
        values = {}
        for level, (attrs, cell) in zip(LEVELS, cells[2:8]):
            config = re.search(r"data-(?:base-)?config='([^']+)'", attrs)
            if not config:
                values[level] = None
                continue
            text = plain(cell)
            lines = re.split(r"<br\s*/?>", cell, flags=re.I)
            # 长度必须来自旋钮之后的独立数据行；不在整格中搜第一个数字。
            length = re.match(r"(?:实测\s*)?([\d.]+)\s*timestep", plain(lines[1])) if len(lines) > 1 else None
            origin_estimate = re.search(r"原估算约\s*([\d.]+)\s*timestep", text)
            if re.search(r"实测\s*[\d.]+\s*timestep", text):
                if not origin_estimate:
                    raise ValueError(f"预计列混入实测且没有原估算：{task}/{level}")
                length = origin_estimate
            windows = re.search(r"/\s*([\d.]+)窗", plain(cell))
            label = re.search(r"<b>(.*?)</b>", cell, re.S)
            if not length or not label:
                raise ValueError(f"历史梯度缺少长度或旋钮：{task}/{level}")
            values[level] = {"config": json.loads(html.unescape(config[1])), "knob": plain(label[1]),
                             "timesteps": float(length[1]), "windows": float(windows[1]) if windows else None,
                             "basis": "原估算近似值" if origin_estimate else ("固定母档参照中位" if level == "mother" else "固定样本集合成中位")}
        result[task] = values
    if list(result) != TASKS:
        raise ValueError("历史梯度任务必须严格按官网 16 任务顺序排列")
    return result


def select_rows(old_rows, v3_rows):
    """选择已批准的成功演示身份；成功选样不能作为全量成功率。"""
    result = []
    for task in TASKS:
        source = v3_rows if task in SELECTED else old_rows
        seeds = SELECTED.get(task) or sorted({r["seed"] for r in source if r["task"] == task})
        if task not in SELECTED and len(seeds) != 1:
            raise ValueError(f"旧批次任务应只有一个演示 seed：{task}")
        for seed in seeds:
            rows = [r for r in source if r["task"] == task and r["seed"] == seed]
            if not rows or len({r["level"] for r in rows}) != len(rows):
                raise ValueError(f"样本不存在或档位重复：{task}/{seed}")
            if any(not r.get("ok") or r.get("task_success") != 1 for r in rows):
                raise ValueError(f"所选演示含失败身份：{task}/{seed}")
            result.extend(rows)
    return result


def assemble(plan, old_rows, v3_rows, metric_rows):
    expected = expected_from_plan(plan)
    selected = select_rows(old_rows, v3_rows)
    metrics = {(r["task"], r["seed"], r["level"]): r for r in metric_rows}
    if len(metrics) != len(metric_rows):
        raise ValueError("H5 指标身份重复")
    identities = {(r["task"], r["seed"], r["level"]) for r in selected}
    if set(metrics) != identities:
        raise ValueError(f"H5 指标身份不全或越界：缺 {sorted(identities-set(metrics))}；多 {sorted(set(metrics)-identities)}")
    tasks = []
    for i, task in enumerate(TASKS):
        number = f"{i // 4 + 1}.{i % 4 + 1}"
        seeds = SELECTED.get(task) or sorted({r["seed"] for r in selected if r["task"] == task})
        samples = []
        for seed in seeds:
            rows = [r for r in selected if r["task"] == task and r["seed"] == seed]
            configured = {level for level, value in expected[task].items() if value is not None}
            if {r["level"] for r in rows} != configured:
                raise ValueError(f"实际档位与配置档位集合不符：{task}/{seed}")
            run = "xhard-1012-swapv3" if task in SELECTED else "xhard-1011"
            batch = "交换 V3：现有成功演示" if task in SELECTED else "10-11 全任务生成"
            source_dir = f"xhard/{run}/report/per_episode_strip"
            if task == "VideoPlaceButton":
                run, batch = "vpbfix-1012", "10-12 VideoPlaceButton 修版"
                source_dir = "xhard/xhard-1011/vpbfix-1012/report/per_episode_strip"
            episode = rows[0]["episode"]
            filename = f"{number}_{task}_ep{episode}_seed{seed}.mp4"
            real_rows = {}
            for row in rows:
                metric = metrics[(task, seed, row["level"])]
                for key in ("timesteps", "demo_timesteps", "exec_timesteps", "demo_windows", "exec_windows", "windows"):
                    if metric[key] != row[key]:
                        raise ValueError(f"H5/summary 不一致：{task}/{seed}/{row['level']}/{key}")
                real_rows[row["level"]] = {k: row[k] for k in ("timesteps", "demo_timesteps", "exec_timesteps", "windows", "demo_windows", "exec_windows", "ratio_timesteps", "ratio_windows")}
                real_rows[row["level"]].update({k: metric[k] for k in ("units", "miss_units", "miss_swaps", "miss", "swap_reason")})
                if metric["miss_swaps"] is None:
                    if task in SELECTED and row["level"] == "mother":
                        real_rows[row["level"]]["swap_reason"] = "母档缺少可核对的交换事件，交换遗漏与合计未统计。"
                    elif task in {"VideoPlaceButton", "VideoPlaceOrder"}:
                        real_rows[row["level"]]["swap_reason"] = f"{task} 的交换事件到录像帧映射尚未验证，交换遗漏与合计未统计。"
                real_rows[row["level"]]["h5"] = metric["h5"]
                for key in ("frames", "swaps", "swap_intervals", "swap_provenance"):
                    if key in metric:
                        real_rows[row["level"]][key] = metric[key]
            samples.append({"seed": seed, "episode": episode, "batch": batch, "run": run,
                            "video_source": f"{source_dir}/{filename}", "video": f"videos/env-results/{run}/{filename}",
                            "rows": real_rows})
        tasks.append({"task": task, "number": number, "expected": expected[task], "samples": samples})
    return {"schema": 1, "source_commit": "a43fa09c94317356091db6ba634a8f167b84ca13",
            "selection": "成功演示选样；不代表全量成功率；只展示已有产物，不补生成。",
            "expected_source": "1006-xhard12-env-plan.html#length-gradient-table",
            "metric_method": "只读 H5 info；以 is_subgoal_boundary 切段；窗口分别按完整 demo/exec 计算；8 帧索引取最近整数。",
            "tasks": tasks}


def validate_snapshot(data):
    if data.get("schema") != 1 or [t["task"] for t in data["tasks"]] != TASKS:
        raise ValueError("统一环境快照结构或任务顺序不符")
    count = 0
    for task in data["tasks"]:
        expected_seeds = SELECTED.get(task["task"])
        samples = task["samples"]
        if expected_seeds and [s["seed"] for s in samples] != expected_seeds:
            raise ValueError("V3 样本身份或顺序错误")
        if not expected_seeds and len(samples) != 1:
            raise ValueError("旧批次应展示一个已有样本")
        if set(task["expected"]) != set(LEVELS):
            raise ValueError("梯度必须显式保留六档")
        for sample in samples:
            configured = {k for k, v in task["expected"].items() if v is not None}
            if set(sample["rows"]) != configured:
                raise ValueError("实测行集合与已配置档位不一致")
            for key in ("video", "video_source"):
                path = pathlib.PurePosixPath(sample[key])
                if path.is_absolute() or ".." in path.parts or path.suffix != ".mp4":
                    raise ValueError("媒体路径越界")
            if not sample["video"].startswith("videos/env-results/"):
                raise ValueError("媒体只能写入新命名空间")
            count += 1
    if count != 22:
        raise ValueError(f"媒体白名单应为 22 条，实为 {count}")


def fmt(value):
    return "未测" if value is None else f"{value:g}"


def sample_note(sample):
    return " ".join(dict.fromkeys(row["swap_reason"] for row in sample["rows"].values()))


def table_rows(task, sample):
    rows = []
    for level in LEVELS:
        label = "母档" if level == "mother" else level
        expected = task["expected"][level]
        if expected is None:
            rows.append(f'<tr class="unconfigured"><th>{label}</th><td colspan="9">缺档：无独立配置</td></tr>')
            continue
        real = sample["rows"].get(level)
        if not real:
            raise ValueError("已配置档位缺少实测行")
        cells = [html.escape(expected["knob"]), fmt(expected["timesteps"]),
                 "待算" if expected["windows"] is None else fmt(expected["windows"]),
                 f'{real["timesteps"]}<small>演示 {real["demo_timesteps"]} ＋ 执行 {real["exec_timesteps"]}</small>',
                 f'{real["windows"]}<small>演示 {real["demo_windows"]} ＋ 执行 {real["exec_windows"]}</small>',
                 f'{real["ratio_timesteps"]:.3f}×<small>窗口 {real["ratio_windows"]:.3f}×</small>',
                 f'{real["miss_units"]} / {real["units"]}', fmt(real["miss_swaps"]), fmt(real["miss"])]
        keys = ["knob", "expected-T", "expected-windows", "actual-T", "windows", "ratio", "miss-actions", "miss-swaps", "miss-total"]
        rows.append(f'<tr data-level="{level}"><th>{label}</th>' + "".join(f'<td data-metric="{key}">{c}</td>' for key, c in zip(keys, cells)) + "</tr>")
    return "".join(rows)


def render(data, history):
    validate_snapshot(data)
    parts = ['<link rel="stylesheet" href="env-results.css">',
             '<section class="env-intro" id="p1-final"><p class="eyebrow">16 个任务 · 22 组已有演示</p><h1 id="p1-videos">二、环境梯度与实测视频</h1>',
             '<p>选择同一母 seed，对照母档与五个难度档的六列录像、实际长度、窗口数和 8 帧采样遗漏。只展示已有产物，不自动补生成。</p>',
             '<div class="evidence-note"><strong>成功演示选样，不代表全量成功率。</strong>三个交换任务各展示 3 个全派生成功 seed，其余任务各 1 个。交换 V3 全量为 130 / 180 成功，50 个任务拒绝，详见 ',
             f'<a href="{SOURCE_BASE}docs/xhard-doc/xhard-1012-swapv3/result.md">完整 V3 结果与拒绝报告</a>。</div>',
             '<p class="method-note">历史预计／母档参照来自原计划：母档为固定参照集合中位，派生档通常为固定母子样本集合成中位；StopCube 的 xhard18 例外，使用原估算约 427 步（窗口未测），不把该格另列的单 seed 实测 423 步当预计。这些值并非当前选定 seed 的预测；请勿把两列差值解释为同 seed 预测误差。窗口按演示段与执行段分别计算后相加：w(L) = max(0, (L − 33) // 16 ＋ 1)，不按每个子目标断窗。</p>',
             '<p class="method-note">8 帧索引为 floor(i × (T − 1) / 7 ＋ 0.5)。动作段按 H5 的 is_subgoal_boundary 切分，排除演示与完成尾段；按原表合并抓放，MoveCube、InsertPeg 每段独立。三个交换任务的 V3 派生档已核实控制步到录像索引映射，按逐交换 50 帧半开区间统计；它们的母档和两个 Place 任务的交换遗漏仍标“未测”。动作列为“遗漏 / 动作总数”。</p>',
             '<p class="method-note"><a href="env-results-data.json">查看冻结指标与来源</a> · <a href="env-results-media.json">查看 22 条媒体白名单</a></p></section>',
             '<nav class="category-nav" aria-label="任务分类">' + "".join(f'<a href="#v-{key}">{i+1} {name}</a>' for i, (key, name) in enumerate(GROUPS)) + '</nav>']
    for i, task in enumerate(data["tasks"]):
        if i % 4 == 0:
            key, name = GROUPS[i // 4]
            parts.append(f'<h2 class="category-title" id="v-{key}">{i//4+1} {name}</h2>')
        sample = task["samples"][0]
        options = "".join(f'<option value="{s["seed"]}">母 seed {s["seed"]}</option>' for s in task["samples"])
        disabled = " disabled" if len(task["samples"]) == 1 else ""
        parts.append(f'<article class="env-card" id="v-{task["number"].replace(".", "-")}" data-task="{task["task"]}" data-seed="{sample["seed"]}"><header><div><span class="task-number">{task["number"]}</span><h3>{task["task"]}</h3></div><label>已有母 seed <select aria-label="{task["task"]} 母 seed"{disabled}>{options}</select></label></header>')
        parts.append(f'<p class="sample-source" aria-live="polite">来源：{sample["batch"]} · seed {sample["seed"]} · episode {sample["episode"]}</p>')
        parts.append('<div class="strip-scroll"><div class="strip-content"><div class="video-levels">' + "".join(f'<span>{"母档" if l == "mother" else l}</span>' for l in LEVELS) + '</div>')
        parts.append(f'<video controls preload="none" playsinline src="{sample["video"]}" aria-label="{task["task"]} seed {sample["seed"]} 六列对照视频"></video></div></div>')
        parts.append('<div class="table-scroll"><table class="result-table"><thead><tr><th rowspan="2">档位</th><th rowspan="2">旋钮</th><th colspan="2">历史预计／母档参照</th><th colspan="3">所选 seed 实测</th><th colspan="3">8 帧遗漏</th></tr><tr><th>参考 T</th><th>参考窗</th><th>实际 T</th><th>实际窗</th><th>相对母档</th><th>动作</th><th>交换</th><th>合计</th></tr></thead><tbody>' + table_rows(task, sample) + '</tbody></table></div>')
        reason = sample_note(sample)
        parts.append(f'<p class="swap-note">{html.escape(reason)}</p></article>')
    parts.append(f'<details class="historical-source"><summary>历史合成图与原计划说明（历史参考，不作为当前运行状态）</summary><p>以下保留原计划的合成图及完整说明；其中旧状态不代表本页选定样本的实际结果。<a href="{SOURCE_BASE}1012-xhard12-env-impl.html">查看完整原实施档案</a></p>{history}</details>')
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    parts.append(f'<script id="env-results-data" type="application/json">{payload}</script><script src="env-results.js" defer></script>')
    return "".join(parts)


def redirect_page():
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>环境梯度与实测视频</title><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><p>实施结果与环境页已合并。<a id="destination" href="envs.html">打开环境梯度与实测视频</a></p><script>
const hash = location.hash;
const target = /^#(?:p1-final|p1-videos|v-(?:counting|permanence|reference|imitation|[1-4]-[1-4]))$/.test(hash) ? hash : '#p1-final';
document.getElementById('destination').href = 'envs.html' + target;
location.replace('envs.html' + target);
</script><noscript><p>请使用上方链接打开合并页。</p></noscript></body></html>'''
