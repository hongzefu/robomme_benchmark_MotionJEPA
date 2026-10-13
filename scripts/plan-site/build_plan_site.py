"""把根目录单文件计划 HTML 拆成托管网页（分页），输出到 artifacts/plan-site/。

页面：index（引言、口径、三行概要、导航）/ impl（实施结果，仅当根目录存在 1012-xhard12-env-impl.html 时生成）/ interface（接口怎么改）/ envs（逐环境与长度）/ goals（逐任务总目标对照）/ review（逐环境物体与动作审查）/ h5（H5 产物一致性检验）/ swap（交换机制调整）/ details（第二部分技术细节）。
根计划里以 base64 内联的 PNG 还原成相对路径引用（data-src），图片另行复制；envs 页的数轴（V2 参照与 V3 各任务的中位条）
由 scripts/plan-site/align_section.py 以「内联数据 + timeline_board.js」直接写在根计划里，本脚本只切页、不再注入。
实施页的 <video> 引用改写为其 data-site-src（videos/<文件名>），对应 mp4 从 --videos-src 复制到站点 videos/，源文件缺失即报错退出。
只读计划文件、实施文件、vis 下的图片与视频源目录，不改仓库任何文件；托管命令见 vis/README.md 同款：
  uv run --no-sync python -m http.server 8092 --bind 0.0.0.0 --directory artifacts/plan-site
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
IMPL_NAV = ("impl.html", "实施结果")
IMPL_CARD = "实施结果（10-12）"
GITHUB_BLOB = "https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/newtask-v3-MotionJepa1006"
NAV = [("index.html", "首页"), ("interface.html", "一、接口怎么改"), ("envs.html", "二、逐环境怎么改与长度对齐"), ("goals.html", "三、逐任务 goal 对照"), ("review.html", "四、逐环境物体与动作审查"), ("h5.html", "五、H5 产物一致性检验"), ("swap.html", "六、交换机制调整"), ("details.html", "技术细节（第二部分）")]


def swap_body(content: pathlib.Path, plan: pathlib.Path) -> str:
    """只提取指定两幅原图及图注，不重新序列化、不修改其字节。"""
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
          swap_plan: pathlib.Path | None = None) -> list[str]:
    nav_items = list(NAV)
    if impl is not None:
        nav_items.insert(1, IMPL_NAV)
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
    cards = "".join(f'<div class="card"><a href="{h}">{IMPL_CARD if (h, t) == IMPL_NAV else t}</a></div>' for h, t in nav_items[1:])
    index_body = intro + sec1 + sec5 + f'<h2 id="nav">页面</h2><div class="cards">{cards}</div>'
    if '<section id="homepage-current-plan">' in main:
        # 首页优先展示本轮简明计划，历史接口和规模只保留为折叠参考。
        current = section(main, r'<section id="homepage-current-plan">', r'</section>') + '</section>'
        history = '<details id="homepage-history"><summary>历史背景与旧方案（不作为本轮实施口径）</summary>' + intro + sec1 + sec5 + '</details>'
        index_body = current + f'<h2 id="nav">页面</h2><div class="cards">{cards}</div>' + history
    pages = {
        "index.html": index_body,
        "interface.html": sec2,
        "envs.html": sec34,
        "goals.html": goals,
        "review.html": review,
        "h5.html": h5,
        "swap.html": swap_body(swap_content or REPO / "scripts/plan-site/swap-content.html",
                               swap_plan or REPO / "1012-swap-pairing-v2-plan.html"),
        "details.html": part2,
    }
    heads = {name: head for name in pages}
    heads["swap.html"] = re.sub(r"<title>.*?</title>", "<title>六、交换机制调整 — RoboMME xhard</title>", head, flags=re.S)
    videos: list[str] = []
    if impl is not None:
        idoc = impl.read_text(encoding="utf-8")
        ihead = idoc[: idoc.index("<body>")]
        # 站点导航与卡片样式（上面注入计划 head 的那一段）同样补进实施页的 <style>
        a0 = head.index("nav.top {")
        site_css = head[a0: head.index("</style>", a0) + len("</style>")]
        ihead = ihead.replace("</style>", site_css, 1)
        ibody, videos = site_videos(section(idoc, r"<main>", r"</main>")[len("<main>"):])
        # 站点里没有根计划与 docs/：计划链接指回站点首页，留档链接指向远端分支上的同路径文件
        ibody = ibody.replace('href="1006-xhard12-env-plan.html"', 'href="index.html"')
        ibody = re.sub(r'href="(docs/[^"]+)"', rf'href="{GITHUB_BLOB}/\1"', ibody)
        pages = {"impl.html": ibody, **pages}
        heads["impl.html"] = ihead
    # 原计划的锚点与说明页不同，统一落在新页首页，避免保留失效锚点。
    pages = {name: re.sub(r'href="1012-swap-pairing-v2-plan\.html(?:#[^"]*)?"',
                          'href="swap.html"', body) for name, body in pages.items()}
    pages["envs.html"] = pages["envs.html"].replace(
        'href="#p1-review"', 'href="review.html#p1-review"')
    pages["goals.html"] = pages["goals.html"].replace(
        'href="#p1-_4"', 'href="envs.html#p1-_4"')
    # 新正文的两份运行档案固定到审查基线；实施页保留其既有链接规则。
    for rel in ("docs/xhard-doc/xhard-1011/result.md",
                "docs/xhard-doc/xhard-1012-swapv2-smoke/result.md"):
        frozen = ("https://github.com/hongzefu/robomme_benchmark_MotionJEPA/blob/"
                  "f98c779a2c3f086759d9fcc4663a06da7deec083/" + rel)
        pages = {name: body if name == "impl.html" else body.replace(
            f'href="{rel}"', f'href="{frozen}"') for name, body in pages.items()}
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
    if videos:
        assert videos_src is not None
        for fn in videos:
            src = videos_src / fn
            if not src.is_file():
                sys.exit(f"视频源文件缺失：{src}")
            dst = out / "videos" / fn
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append("videos/" + fn)
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
                    help="实施结果 HTML；文件不存在或传空串时不生成 impl.html")
    ap.add_argument("--swap-content", default=str(REPO / "scripts/plan-site/swap-content.html"),
                    help="交换页正文片段，含两幅原图占位符")
    ap.add_argument("--swap-plan", default=str(REPO / "1012-swap-pairing-v2-plan.html"),
                    help="只读取图 2、图 3 及原图注的来源计划")
    ap.add_argument("--videos-src", default=str(REPO / "artifacts" / "xhard" / "xhard-1011" / "report" / "per_episode_strip"),
                    help="实施页视频的源目录（按文件名查找）")
    a = ap.parse_args()
    impl = pathlib.Path(a.impl) if a.impl and pathlib.Path(a.impl).is_file() else None
    written = build(pathlib.Path(a.plan), pathlib.Path(a.out), impl, pathlib.Path(a.videos_src),
                    swap_content=pathlib.Path(a.swap_content), swap_plan=pathlib.Path(a.swap_plan))
    pages = [w for w in written if w.endswith(".html")]
    videos = [w for w in written if w.startswith("videos/")]
    images = sum(w.endswith((".png", ".jpg", ".svg")) for w in written)
    documents = len(written) - len(pages) - len(videos) - images
    print(f"PLAN_SITE=OK pages={len(pages)} images={images} videos={len(videos)} documents={documents} out={a.out}")


if __name__ == "__main__":
    main()
