"""把根目录单文件计划 HTML 拆成托管网页（分页），输出到 artifacts/plan-site/。

页面：index / interface / envs（环境梯度与实测视频合并页）/ goals / review / h5 / swap / details。
impl.html 保留为兼容重定向，共八个导航正文页与一个重定向页。根计划的内联 PNG 按 data-src 复制，
envs 页读取已核实的 env-results-data.json，只展示实测指标与真实分段数轴。
16 条媒体白名单相对于 --artifact-root 定位，复制到独立 videos/env-results/；缺源文件即拒绝构建。
只读计划、冻结快照与图片视频源，不改输入；托管命令见 vis/README.md 同款：
  uv run --no-sync python -m http.server 8092 --bind 0.0.0.0 --directory artifacts/plan-site
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

from env_results import render as render_env_results, redirect_page, validate_snapshot

REPO = pathlib.Path(__file__).resolve().parents[2]
GITHUB_BLOB = "https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/newtask-v3-MotionJepa1006"
NAV = [("index.html", "首页"), ("interface.html", "一、接口怎么改"), ("envs.html", "二、环境梯度与实测视频"), ("goals.html", "三、逐任务 goal 对照"), ("review.html", "四、逐环境物体与动作审查"), ("h5.html", "五、H5 产物一致性检验"), ("swap.html", "六、交换机制调整"), ("details.html", "技术细节（第二部分）")]


def swap_body(content: pathlib.Path, plan: pathlib.Path,
              v3_plan: pathlib.Path | None = None) -> str:
    """提取 V3 流程图及两幅历史原图；旧正文的两参数调用仍可用。"""
    doc = plan.read_bytes().decode("utf-8")
    figures = re.findall(r"<figure\b[^>]*>.*?</figure>", doc, flags=re.S)
    body = content.read_bytes().decode("utf-8")
    for token, marker in (
        ("{{SWAP_FIGURE_2}}", 'src="docs/xhard-doc/xhard-1012-swap-v2-probe/probe_g.png"'),
        ("{{SWAP_FIGURE_3}}", "<figcaption>图 3　配对机制流程对比："),
    ):
        matches = [figure for figure in figures if marker in figure]
        if len(matches) != 1 or body.count(token) != 1:
            raise ValueError(f"交换页原图提取数量不符：{token} 原图={len(matches)} 占位符={body.count(token)}")
        body = body.replace(token, matches[0])
    token = "{{SWAP_V3_FIGURE_1}}"
    if token in body or v3_plan is not None:
        v3_doc = (v3_plan or REPO / "1012-swap-min3kinds-v3-plan.html").read_bytes().decode("utf-8")
        matches = [figure for figure in re.findall(r"<figure\b[^>]*>.*?</figure>", v3_doc, flags=re.S)
                   if "<figcaption>图 1　配对机制流程对比：" in figure]
        if len(matches) != 1 or body.count(token) != 1:
            raise ValueError(f"交换页原图提取数量不符：{token} 原图={len(matches)} 占位符={body.count(token)}")
        body = body.replace(token, matches[0])
    return body


def section(doc: str, start_pat: str, end_pat: str) -> str:
    a = re.search(start_pat, doc)
    assert a, start_pat
    b = re.search(end_pat, doc[a.end():])
    assert b, end_pat
    return doc[a.start(): a.end() + b.start()]


def site_videos(body: str) -> tuple[str, list[str]]:
    """把 <video ... src="..." data-site-src="videos/x.mp4"> 的 src 改写为 data-site-src，返回改写后正文与视频文件名。"""
    names: list[str] = []

    def fix(m: re.Match) -> str:
        tag = m.group(0)
        site = re.search(r'data-site-src="([^"]+)"', tag)
        if not site:
            sys.exit(f"实施页 <video> 缺 data-site-src：{tag[:120]}")
        rel = site.group(1)
        if not rel.startswith("videos/") or "/" in rel[len("videos/"):]:
            sys.exit(f"data-site-src 必须形如 videos/<文件名>：{rel}")
        names.append(rel[len("videos/"):])
        return re.sub(r'\ssrc="[^"]*"', f' src="{rel}"', tag, count=1)

    return re.sub(r"<video\b[^>]*>", fix, body), names


def build(plan: pathlib.Path, out: pathlib.Path, impl: pathlib.Path | None = None,
          videos_src: pathlib.Path | None = None, *, swap_content: pathlib.Path | None = None,
          swap_plan: pathlib.Path | None = None,
          swap_v3_plan: pathlib.Path | None = None,
          artifact_root: pathlib.Path | None = None,
          env_data: pathlib.Path | None = None) -> list[str]:
    nav_items = list(NAV)
    artifact_root = artifact_root if artifact_root is not None else REPO / "artifacts"
    if not artifact_root.is_dir():
        raise FileNotFoundError(f"明确指定的产物根不存在：{artifact_root}")
    data = json.loads((env_data or REPO / "scripts/plan-site/env-results-data.json").read_text(encoding="utf-8"))
    validate_snapshot(data)
    media = [(sample["video_source"], sample["video"]) for task in data["tasks"] for sample in task["samples"]]
    if len({dst for _, dst in media}) != len(media):
        raise ValueError("媒体白名单目标重复")
    # 完整检查后才开始写站点；缺任何媒体即拒绝，不回退旧批次。
    for source, _ in media:
        if not (artifact_root / source).is_file():
            raise FileNotFoundError(f"白名单视频缺失：{artifact_root / source}")
    doc = plan.read_text(encoding="utf-8")
    # base64 内联图还原成相对路径（站点按路径复制图片，页面不背几 MB 的 base64）
    doc = re.sub(r'src="data:image/[^"]*"\s+data-src="([^"]+)"', r'src="\1"', doc)
    head = doc[: doc.index("<body>")]
    head = head.replace("</style>", (
        "nav.top { display:flex; gap:18px; flex-wrap:wrap; padding:10px 0 14px; border-bottom:2px solid var(--border); margin-bottom:18px; font-size:15px; }\n"
        "nav.top a { color:var(--muted); text-decoration:none; padding:4px 8px; border-radius:6px; }\n"
        "nav.top a.cur { color:#fff; background:var(--accent); }\n"
        "blockquote code { overflow-wrap:anywhere; }\n"
        ".cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:14px; margin:18px 0; }\n"
        ".card { border:1px solid var(--border); border-radius:8px; padding:14px 16px; }\n"
        ".card a { font-weight:600; font-size:1.05em; }\n</style>"))
    main = section(doc, r"<main>", r"</main>")
    intro = section(main, r"<h1 id=\"[^\"]*\">1006-xhard12-env-plan", r"<h1 id=\"[^\"]*\">第一部分")
    sec1 = section(main, r"<h2 id=\"p1-_2\">", r"<h2 id=\"p1-_3\">")        # 一、口径
    sec2 = section(main, r"<h2 id=\"p1-_3\">", r"<h2 id=\"p1-_4\">")        # 二、接口
    sec34 = section(main, r"<h2 id=\"p1-_4\">", r"<h2 id=\"p1-goals\">")    # 对齐与逐环境讨论，含内联数轴
    # 分页后任务说明位于技术细节页；根计划仍保留页内锚点。
    sec34 = re.sub(r'href="#(knob-[^"]+)"', r'href="details.html#\1"', sec34)
    goals = section(main, r"<h2 id=\"p1-goals\">", r"<h2 id=\"p1-review\">")
    review = section(main, r"<h2 id=\"p1-review\">", r"<h2 id=\"p1-h5\">")  # 四、逐环境物体与动作审查
    h5 = section(main, r"<h2 id=\"p1-h5\">", r"<h2 id=\"p1-_6\">")  # 五、H5 产物一致性检验
    sec5 = section(main, r"<h2 id=\"p1-_6\">", r"<h1 id=\"[^\"]*\">第二部分")  # 五、三行
    part2 = main[re.search(r"<h1 id=\"[^\"]*\">第二部分", main).start():]
    cards = "".join(f'<div class="card"><a href="{h}">{t}</a></div>' for h, t in nav_items[1:])
    index_body = intro + sec1 + sec5 + f'<h2 id="nav">页面</h2><div class="cards">{cards}</div>'
    if '<section id="homepage-current-plan">' in main:
        # 首页优先展示本轮简明计划，历史接口和规模只保留为折叠参考。
        current = section(main, r'<section id="homepage-current-plan">', r'</section>') + '</section>'
        history = '<details id="homepage-history"><summary>历史背景与旧方案（不作为本轮实施口径）</summary>' + intro + sec1 + sec5 + '</details>'
        index_body = current + f'<h2 id="nav">页面</h2><div class="cards">{cards}</div>' + history
    pages = {
        "index.html": index_body,
        "interface.html": sec2,
        "envs.html": render_env_results(data),
        "goals.html": goals,
        "review.html": review,
        "h5.html": h5,
        "swap.html": swap_body(swap_content or REPO / "scripts/plan-site/swap-content.html",
                               swap_plan or REPO / "1012-swap-pairing-v2-plan.html", swap_v3_plan),
        "details.html": part2,
    }
    heads = {name: head for name in pages}
    heads["swap.html"] = re.sub(r"<title>.*?</title>", "<title>六、交换机制调整 — RoboMME xhard</title>", head, flags=re.S)
    heads["envs.html"] = re.sub(r"<title>.*?</title>", "<title>环境梯度与实测视频 — RoboMME xhard</title>", head, flags=re.S)
    # 原计划的锚点与说明页不同，统一落在新页首页，避免保留失效锚点。
    pages = {name: re.sub(r'href="1012-swap-(?:pairing-v2|min3kinds-v3)-plan\.html(?:#[^"]*)?"',
                          'href="swap.html"', body) for name, body in pages.items()}
    pages["envs.html"] = pages["envs.html"].replace(
        'href="#p1-review"', 'href="review.html#p1-review"')
    pages["goals.html"] = pages["goals.html"].replace(
        'href="#p1-_4"', 'href="envs.html#p1-_4"')
    # 分页编号跟随站点导航；根计划仍保留自身的章节编号。
    pages["envs.html"] = pages["envs.html"].replace(
        '<h2 id="p1-_4">三、现行环境与五档配置</h2>',
        '<h2 id="p1-_4">二、现行环境与五档配置</h2>')
    pages["goals.html"] = pages["goals.html"].replace(
        '<h2 id="p1-goals">五、现行总目标与子目标对照</h2>',
        '<h2 id="p1-goals">三、现行总目标与子目标对照</h2>')
    # 新正文的两份运行档案固定到审查基线；实施页保留其既有链接规则。
    for rel in ("docs/xhard-doc/xhard-1011/result.md",
                "docs/xhard-doc/xhard-1012-swapv2-smoke/result.md"):
        frozen = ("https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/"
                  "f98c779a2c3f086759d9fcc4663a06da7deec083/" + rel)
        pages = {name: body if name == "impl.html" else body.replace(
            f'href="{rel}"', f'href="{frozen}"') for name, body in pages.items()}
    # V3 结果使用本轮固定提交；旧图、旧运行与实施页链接保留各自身份。
    v3_blob = ("https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/"
               "522125e29906d03595a562e51c1898291da2f15f/")
    pages = {name: body if name == "impl.html" else re.sub(
        r'href="(docs/xhard-doc/xhard-1012-swapv3/[^"]+)"',
        lambda match: f'href="{v3_blob}{match.group(1)}"', body)
        for name, body in pages.items()}
    # 首页历史参照不随站点复制；只改这一条已知引用，冻结到本轮源码版本。
    reference = "1006-xhard12-prev-training-and-task-plan.md"
    frozen_reference = (
        "https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/"
        "f98c779a2c3f086759d9fcc4663a06da7deec083/" + reference
    )
    pages["index.html"] = pages["index.html"].replace(
        f'href="{reference}"', f'href="{frozen_reference}"')
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, body in pages.items():
        nav = '<nav class="top">' + "".join(
            f'<a href="{h}" class="{"cur" if h == name else ""}">{t}</a>' for h, t in nav_items) + "</nav>"
        html = heads[name] + f'<body>\n<div class="wrap">\n<main>\n{nav}\n{body}\n</main>\n</div>\n</body>\n</html>\n'
        (out / name).write_text(html, encoding="utf-8")
        written.append(name)
    (out / "impl.html").write_text(redirect_page(), encoding="utf-8")
    written.append("impl.html")
    for source, target in media:
        dst = out / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact_root / source, dst)
        written.append(target)
    for name in ("env-results.js", "env-results.css", "env-results-data.json"):
        source = (env_data or REPO / "scripts/plan-site/env-results-data.json") if name.endswith(".json") else REPO / "scripts/plan-site" / name
        shutil.copy2(source, out / name)
        written.append(name)
    (out / "env-results-media.json").write_text(json.dumps(
        [{"source": source, "destination": target} for source, target in media], ensure_ascii=False, indent=2), encoding="utf-8")
    written.append("env-results-media.json")
    # 页面内引用的仓库相对路径图片，按原相对路径复制到站点目录
    for rel in sorted(set(re.findall(r'src="((?:vis|docs)/[^"]+\.(?:png|jpg|svg))"', "".join(pages.values())))):
        src = REPO / rel
        assert src.is_file(), rel
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(rel)
    # 仅发布明确列出的站内证据，不遍历 docs，也不依赖尚未推送的远端提交。
    for rel in ("docs/site-review/1012-frozen-site-audit.md",):
        if f'href="{rel}"' not in "".join(pages.values()):
            continue
        src = REPO / rel
        if not src.is_file():
            raise FileNotFoundError(f"站内证据源文件缺失：{src}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(rel)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", default=str(REPO / "1006-xhard12-env-plan.html"))
    ap.add_argument("--out", default=str(REPO / "artifacts" / "plan-site"))
    ap.add_argument("--impl", default=str(REPO / "1012-xhard12-env-impl.html"),
                    help="保留旧命令兼容性；impl.html 现在固定重定向到 envs.html")
    ap.add_argument("--swap-content", default=str(REPO / "scripts/plan-site/swap-content.html"),
                    help="交换页正文片段，含 V3 流程图与两幅历史原图占位符")
    ap.add_argument("--swap-plan", default=str(REPO / "1012-swap-pairing-v2-plan.html"),
                    help="只读取图 2、图 3 及原图注的来源计划")
    ap.add_argument("--swap-v3-plan", default=None,
                    help="V3 图 1 来源计划；省略时按正文占位符自动读取仓库内现行计划")
    ap.add_argument("--videos-src", default=str(REPO / "artifacts" / "xhard" / "xhard-1011" / "report" / "per_episode_strip"),
                    help="保留旧命令兼容性；统一页仅使用快照中的明确媒体白名单")
    ap.add_argument("--artifact-root", type=pathlib.Path, default=REPO / "artifacts",
                    help="现有产物根；明确缺失时报错，不回退其他目录")
    ap.add_argument("--env-data", type=pathlib.Path, default=REPO / "scripts/plan-site/env-results-data.json",
                    help="已核实的统一环境数据快照")
    a = ap.parse_args()
    impl = pathlib.Path(a.impl) if a.impl and pathlib.Path(a.impl).is_file() else None
    written = build(pathlib.Path(a.plan), pathlib.Path(a.out), impl, pathlib.Path(a.videos_src),
                    swap_content=pathlib.Path(a.swap_content), swap_plan=pathlib.Path(a.swap_plan),
                    swap_v3_plan=pathlib.Path(a.swap_v3_plan) if a.swap_v3_plan else None,
                    artifact_root=a.artifact_root, env_data=a.env_data)
    pages = [w for w in written if w.endswith(".html")]
    videos = [w for w in written if w.startswith("videos/")]
    images = sum(w.endswith((".png", ".jpg", ".svg")) for w in written)
    documents = len(written) - len(pages) - len(videos) - images
    print(f"PLAN_SITE=OK pages={len(pages)} images={images} videos={len(videos)} documents={documents} out={a.out}")


if __name__ == "__main__":
    main()
