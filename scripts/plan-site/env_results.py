"""统一环境页：真实录像指标、H5 时间轴与严格媒体白名单。"""
from __future__ import annotations

import html
import json
import math
import pathlib
import re

TASKS = ["BinFill", "PickXtimes", "SwingXtimes", "StopCube", "VideoUnmask", "ButtonUnmask",
         "VideoUnmaskSwap", "ButtonUnmaskSwap", "PickHighlight", "VideoRepick", "VideoPlaceButton",
         "VideoPlaceOrder", "MoveCube", "InsertPeg", "PatternLock", "RouteStick"]
LEVELS = ["mother", "xhard12", "xhard14", "xhard16", "xhard18", "xhard20"]
SELECTED = {"VideoUnmaskSwap": [5700], "ButtonUnmaskSwap": [7700], "VideoRepick": [9600]}
GROUPS = [("counting", "计数"), ("permanence", "永久性"), ("reference", "参考"), ("imitation", "模仿")]
SOURCE_BASE = "https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/a43fa09c94317356091db6ba634a8f167b84ca13/"


def plain(value):
    # 标签是文本边界，不能把旋钮末尾数字与下一行长度拼成新数字。
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def configurations_from_plan(doc):
    """只读取各档的配置键与旋钮，不读取长度或窗口参考数字。"""
    match = re.search(r'<table id="length-gradient-table">(.*?)</table>', doc, re.S)
    if not match:
        raise ValueError("缺少配置梯度表")
    result = {}
    for task, body in re.findall(r'<tr data-task="([^"]+)">(.*?)</tr>', match[1], re.S):
        cells = re.findall(r'<td\b([^>]*)>(.*?)</td>', body, re.S)
        if len(cells) != 9:
            raise ValueError(f"配置梯度列数错误：{task}")
        values = {}
        for level, (attrs, cell) in zip(LEVELS, cells[2:8]):
            config = re.search(r"data-(?:base-)?config='([^']+)'", attrs)
            if not config:
                values[level] = None
                continue
            label = re.search(r"<b>(.*?)</b>", cell, re.S)
            if not label:
                raise ValueError(f"配置梯度缺少旋钮：{task}/{level}")
            values[level] = {"config": json.loads(html.unescape(config[1])), "knob": plain(label[1])}
        result[task] = values
    if list(result) != TASKS:
        raise ValueError("配置梯度任务必须严格按官网 16 任务顺序排列")
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
    configurations = configurations_from_plan(plan)
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
            configured = {level for level, value in configurations[task].items() if value is not None}
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
                for key in ("segments", "missed_units", "frames", "swaps", "swap_intervals", "swap_provenance"):
                    if key in metric:
                        real_rows[row["level"]][key] = metric[key]
            samples.append({"seed": seed, "episode": episode, "batch": batch, "run": run,
                            "video_source": f"{source_dir}/{filename}", "video": f"videos/env-results/{run}/{filename}",
                            "rows": real_rows})
        tasks.append({"task": task, "number": number, "configurations": configurations[task], "samples": samples})
    return {"schema": 2, "source_commit": "a43fa09c94317356091db6ba634a8f167b84ca13",
            "selection": "成功演示选样；不代表全量成功率；只展示已有产物，不补生成。",
            "metric_method": "只读 H5 info；以 is_subgoal_boundary 切段；窗口分别按完整 demo/exec 计算；8 帧索引取最近整数。",
            "tasks": tasks}


def validate_timeline(row):
    total, demo = row["timesteps"], row["demo_timesteps"]
    if total <= 0 or demo < 0 or demo > total or row["exec_timesteps"] != total - demo:
        raise ValueError("实测长度不一致")
    window_count = lambda n: max(0, (n - 33) // 16 + 1)
    if (row["demo_windows"] != window_count(demo) or row["exec_windows"] != window_count(total - demo)
            or row["windows"] != row["demo_windows"] + row["exec_windows"]):
        raise ValueError("实测窗口与完整演示／执行段不符")
    cursor = 0
    for segment in row["segments"]:
        start, end = segment["start"], segment["end"]
        if start != cursor or not start < end <= total or not isinstance(segment["text"], str):
            raise ValueError("原始分段没有连续覆盖录像")
        if (segment["demo"] and end > demo) or (not segment["demo"] and start < demo):
            raise ValueError("原始分段跨过演示／执行边界")
        cursor = end
    if cursor != total:
        raise ValueError("原始分段未覆盖至录像结尾")
    frames = [math.floor(i * (total - 1) / 7 + .5) for i in range(8)]
    if row["frames"] != frames or len(row["missed_units"]) != row["miss_units"]:
        raise ValueError("采样帧或遗漏动作数不符")
    for start, end, label in row["missed_units"]:
        if not demo <= start < end <= total or any(start <= f < end for f in frames) or not isinstance(label, str):
            raise ValueError("遗漏动作区间不符")
    intervals = row.get("swap_intervals", [])
    if row["miss_swaps"] is None:
        if intervals or row["miss"] is not None:
            raise ValueError("未知交换不得出现事件或总遗漏数")
    else:
        if any(not 0 <= a < b <= total for a, b in intervals):
            raise ValueError("交换区间越界")
        if len(intervals) != row.get("swaps", 0):
            raise ValueError("交换区间数量不符")
        missed = sum(not any(a <= f < b for f in frames) for a, b in intervals)
        if row["miss_swaps"] != missed or row["miss"] != row["miss_units"] + missed:
            raise ValueError("交换或总遗漏与区间不符")


def validate_snapshot(data):
    if data.get("schema") != 2 or [t["task"] for t in data["tasks"]] != TASKS:
        raise ValueError("统一环境快照结构或任务顺序不符")
    count = 0
    for task in data["tasks"]:
        expected_seeds = SELECTED.get(task["task"])
        samples = task["samples"]
        if expected_seeds and [s["seed"] for s in samples] != expected_seeds:
            raise ValueError("V3 样本身份或顺序错误")
        if not expected_seeds and len(samples) != 1:
            raise ValueError("旧批次应展示一个已有样本")
        if set(task["configurations"]) != set(LEVELS):
            raise ValueError("梯度必须显式保留六档")
        for value in task["configurations"].values():
            if value is not None and set(value) != {"config", "knob"}:
                raise ValueError("配置只允许配置键与旋钮说明")
        for sample in samples:
            configured = {k for k, v in task["configurations"].items() if v is not None}
            if set(sample["rows"]) != configured:
                raise ValueError("实测行集合与已配置档位不一致")
            for key in ("video", "video_source"):
                path = pathlib.PurePosixPath(sample[key])
                if path.is_absolute() or ".." in path.parts or path.suffix != ".mp4":
                    raise ValueError("媒体路径越界")
            if not sample["video"].startswith("videos/env-results/"):
                raise ValueError("媒体只能写入新命名空间")
            for row in sample["rows"].values():
                validate_timeline(row)
            count += 1
    if count != 16:
        raise ValueError(f"媒体白名单应为 16 条，实为 {count}")


def fmt(value):
    return "未测" if value is None else f"{value:g}"


def sample_note(sample):
    return " ".join(dict.fromkeys(row["swap_reason"] for row in sample["rows"].values()))


def table_row(task, sample):
    name = task["task"]
    cells = [f'<tr data-task="{name}" data-seed="{sample["seed"]}"><th scope="row"><span class="task-number">{task["number"]}</span><strong>{name}</strong><small>母 seed {sample["seed"]}</small><span class="task-links"><a href="#timeline-{name}">数轴</a> · <a href="#v-{task["number"].replace(".", "-")}">视频</a></span></th>']
    for level in LEVELS:
        configuration = task["configurations"][level]
        if configuration is None:
            cells.append(f'<td class="unconfigured" data-level="{level}" data-missing="true">缺档<small>无独立配置</small></td>')
            continue
        real = sample["rows"].get(level)
        if not real:
            raise ValueError("已配置档位缺少实测行")
        details = f'演示 {real["demo_timesteps"]} 帧 / {real["demo_windows"]} 窗；执行 {real["exec_timesteps"]} 帧 / {real["exec_windows"]} 窗；窗口倍率 {real["ratio_windows"]:.3f}×'
        cells.append(f'<td data-level="{level}" data-missing="false" title="{details}"><span class="cell-knob" data-metric="knob">{html.escape(configuration["knob"])}</span><span class="cell-length"><b data-metric="actual-T">{real["timesteps"]}</b> 步 / <b data-metric="windows">{real["windows"]}</b> 窗</span><span class="cell-ratio" data-metric="ratio">{real["ratio_timesteps"]:.3f}×</span><span class="cell-miss">漏：动 <b data-metric="miss-actions">{real["miss_units"]}/{real["units"]}</b> · 换 <b data-metric="miss-swaps">{fmt(real["miss_swaps"])}</b> · 总 <b data-metric="miss-total">{fmt(real["miss"])}</b></span></td>')
    return "".join(cells) + "</tr>"


def render(data):
    validate_snapshot(data)
    parts = ['<link rel="stylesheet" href="env-results.css">',
             '<section class="env-intro"><p class="eyebrow">16 个任务 · 16 个固定母 seed · 68 个实测身份</p><h1>二、环境梯度与实测视频</h1>',
             '<p>先看所有任务的紧凑总表，再看 16 张数轴，最后看 16 个六列视频。每个任务固定一个已有母 seed，三处使用同一份实测数据。</p>',
             '<div class="evidence-note"><strong>成功演示选样，不代表全量成功率。</strong>VideoUnmaskSwap 固定 seed 5700，ButtonUnmaskSwap 固定 7700，VideoRepick 固定 9600；其余任务沿用已有默认样本。交换 V3 全量为 130 / 180 成功，50 个任务拒绝，详见 ',
             f'<a href="{SOURCE_BASE}docs/xhard-doc/xhard-1012-swapv3/result.md">完整 V3 结果与拒绝报告</a>。</div>',
             '<p class="method-note">长度与倍率均为同一 seed 的实测，倍率以其母档为分母；缺档没有独立配置。遗漏标记“动 / 换 / 总”分别表示动作、交换与合计；动作写作“遗漏数 / 动作总数”，未知项显示“未测”。</p>',
             '<p class="method-note"><a href="env-results-data.json">查看冻结实测指标与分段</a> · <a href="env-results-media.json">查看 16 条媒体白名单</a></p></section>',
             '<nav class="section-nav" aria-label="本页内容"><a href="#p1-final">紧凑总表</a><a href="#actual-timelines">16 张实测数轴</a><a href="#p1-videos">16 个实测视频</a></nav>',
             '<section class="actual-overview" id="p1-final"><span id="p1-_4"></span><h2>所有任务的实测总表</h2><div class="table-scroll"><table class="compact-results"><thead><tr><th>任务 / 固定母 seed</th>' + ''.join(f'<th>{"母档" if level == "mother" else level}</th>' for level in LEVELS) + '</tr></thead><tbody>']
    parts.extend(table_row(task, task["samples"][0]) for task in data["tasks"])
    parts.append('</tbody></table></div></section>')
    parts.extend(['<section class="timelines-block" id="actual-timelines"><h2>16 张实测数轴</h2>',
             '<p class="method-note">每个任务的六档共用绝对 T 轴，以该 seed 最长一档为上限；缺档不绘制数据。33 帧窗口按步长 16，在完整演示段与执行段各自铺设：w(L) = max(0, (L − 33) // 16 ＋ 1)，不按子目标断窗。</p>',
             '<p class="method-note">8 帧索引为 floor(i × (T − 1) / 7 ＋ 0.5)。动作段按 H5 的 is_subgoal_boundary 切分，排除演示与完成尾段；按原表合并抓放，MoveCube、InsertPeg 每段独立。三个交换任务的 V3 派生档已核实控制步到录像索引映射，按逐交换 50 帧半开区间统计；它们的母档和两个 Place 任务的交换遗漏仍标“未测”。动作列为“遗漏 / 动作总数”。</p>',
             '<p class="method-note">数轴中的原始子目标分段直接来自 H5 边界，与合并后的动作单元不同；红色覆盖表示被 8 帧遗漏的合并动作区间。悬停或点选分段、窗口、交换条可查看区间与标签；长标签不会挤进图内。</p>'])
    for task in data["tasks"]:
        sample = task["samples"][0]
        parts.append(f'<article class="timeline-card" id="timeline-{task["task"]}" data-task="{task["task"]}" data-seed="{sample["seed"]}"><header><h3>{task["number"]} {task["task"]}</h3><span>母 seed {sample["seed"]} · <a href="#v-{task["number"].replace(".", "-")}">查看视频</a></span></header><div class="timeline-legend"><span class="legend-demo">演示</span><span class="legend-exec">执行</span><span class="legend-segment">原始分段</span><span class="legend-window">33 帧窗口</span><span class="legend-missed">遗漏动作</span><span class="legend-swap">已核实交换</span><span class="legend-frame">8 帧采样点</span></div><div class="actual-timeline" aria-label="实测时间轴"><noscript>启用 JavaScript 后可查看真实分段数轴，实测总表仍可直接阅读。</noscript></div><p class="timeline-detail" aria-live="polite">悬停或点选图中条带查看详情。</p><p class="swap-note">{html.escape(sample_note(sample))}</p></article>')
    parts.append('</section><section class="videos-block" id="p1-videos"><h2>16 个实测视频</h2><p class="method-note">每任务一个已有六列视频，列顺序为母档、xhard12、xhard14、xhard16、xhard18、xhard20；缺档仍以影片中的空列表示。按需播放，不自动加载所有录像。</p>')
    for i, task in enumerate(data["tasks"]):
        sample = task["samples"][0]
        if i % 4 == 0:
            parts.append(f'<span class="legacy-anchor" id="v-{GROUPS[i // 4][0]}"></span>')
        parts.append(f'<article class="video-card" id="v-{task["number"].replace(".", "-")}" data-task="{task["task"]}" data-seed="{sample["seed"]}"><header><h3>{task["number"]} {task["task"]}</h3><a href="#timeline-{task["task"]}">查看数轴</a></header><p class="sample-source">来源：{sample["batch"]} · seed {sample["seed"]} · episode {sample["episode"]}</p>')
        parts.append('<div class="strip-scroll"><div class="strip-content"><div class="video-levels">' + "".join(f'<span>{"母档" if l == "mother" else l}</span>' for l in LEVELS) + '</div>')
        parts.append(f'<video controls preload="none" playsinline src="{sample["video"]}" aria-label="{task["task"]} seed {sample["seed"]} 六列对照视频"></video></div></div></article>')
    parts.append('</section>')
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
