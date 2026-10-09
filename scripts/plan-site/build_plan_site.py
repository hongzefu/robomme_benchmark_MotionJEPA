"""把根目录单文件计划 HTML 拆成托管网页（分页），输出到 artifacts/plan-site/。

页面：index（引言、口径、三行概要、导航）/ interface（接口怎么改）/ envs（逐环境怎么改、改完长度怎么对齐）/ details（第二部分技术细节）。
根计划里以 base64 内联的 PNG 还原成相对路径引用（data-src），图片另行复制；envs 页的两张数轴总览（xhard1 合成、V2 实测）
不用 PNG，改为内联数据在浏览器里画 SVG（timeline_boards.py + timeline_board.js，2026-10-08 用户要求「原生在浏览器内部渲染」）。
只读计划文件与 vis 下的数据与 PNG，不改仓库任何文件；托管命令见 vis/README.md 同款：
  uv run --no-sync python -m http.server 8092 --bind 0.0.0.0 --directory artifacts/plan-site
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import timeline_boards  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
NAV = [("index.html", "首页"), ("interface.html", "一、接口怎么改"), ("envs.html", "二、逐环境怎么改与长度对齐"), ("details.html", "技术细节（第二部分）")]


def section(doc: str, start_pat: str, end_pat: str) -> str:
    a = re.search(start_pat, doc)
    assert a, start_pat
    b = re.search(end_pat, doc[a.end():])
    assert b, end_pat
    return doc[a.start(): a.end() + b.start()]


def boards(body: str) -> str:
    """把两张数轴总览 PNG 换成浏览器内渲染的 figure，并在页尾挂数据与画图脚本。"""
    for rel, key in timeline_boards.BOARD_OF_IMAGE.items():
        pat = r'<p><img alt="([^"]*)" src="' + re.escape(rel) + r'" */?></p>'
        body, n = re.subn(pat, lambda m: timeline_boards.figure_html(key, m.group(1)), body)
        assert n == 1, (rel, n)
    script, rows = timeline_boards.script_html()
    print(f"TIMELINE_BOARDS=OK " + " ".join(f"{k}_rows={v}" for k, v in rows.items()))
    return body + script


def build(plan: pathlib.Path, out: pathlib.Path) -> list[str]:
    doc = plan.read_text(encoding="utf-8")
    # base64 内联图还原成相对路径（站点按路径复制图片，页面不背几 MB 的 base64）
    doc = re.sub(r'src="data:image/[^"]*"\s+data-src="([^"]+)"', r'src="\1"', doc)
    head = doc[: doc.index("<body>")]
    head = head.replace("</style>", (
        "nav.top { display:flex; gap:18px; flex-wrap:wrap; padding:10px 0 14px; border-bottom:2px solid var(--border); margin-bottom:18px; font-size:15px; }\n"
        "nav.top a { color:var(--muted); text-decoration:none; padding:4px 8px; border-radius:6px; }\n"
        "nav.top a.cur { color:#fff; background:var(--accent); }\n"
        ".cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:14px; margin:18px 0; }\n"
        ".card { border:1px solid var(--border); border-radius:8px; padding:14px 16px; }\n"
        ".card a { font-weight:600; font-size:1.05em; }\n" + timeline_boards.CSS + "</style>"))
    main = section(doc, r"<main>", r"</main>")
    intro = section(main, r"<h1 id=\"[^\"]*\">1006-xhard12-env-plan", r"<h1 id=\"[^\"]*\">第一部分")
    sec1 = section(main, r"<h2 id=\"p1-_2\">", r"<h2 id=\"p1-_3\">")        # 一、口径
    sec2 = section(main, r"<h2 id=\"p1-_3\">", r"<h2 id=\"p1-_4\">")        # 二、接口
    sec34 = section(main, r"<h2 id=\"p1-_4\">", r"<h2 id=\"p1-_5\">")       # 三、四
    sec5 = section(main, r"<h2 id=\"p1-_5\">", r"<h1 id=\"[^\"]*\">第二部分")  # 五、三行
    part2 = main[re.search(r"<h1 id=\"[^\"]*\">第二部分", main).start():]
    cards = "".join(f'<div class="card"><a href="{h}">{t}</a></div>' for h, t in NAV[1:])
    pages = {
        "index.html": intro + sec1 + sec5 + f'<h2 id="nav">页面</h2><div class="cards">{cards}</div>',
        "interface.html": sec2,
        "envs.html": boards(sec34),
        "details.html": part2,
    }
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, body in pages.items():
        nav = '<nav class="top">' + "".join(
            f'<a href="{h}" class="{"cur" if h == name else ""}">{t}</a>' for h, t in NAV) + "</nav>"
        html = head + f'<body>\n<div class="wrap">\n<main>\n{nav}\n{body}\n</main>\n</div>\n</body>\n</html>\n'
        (out / name).write_text(html, encoding="utf-8")
        written.append(name)
    # 页面内引用的仓库相对路径图片，按原相对路径复制到站点目录
    for rel in sorted(set(re.findall(r'src="((?:vis|docs)/[^"]+\.(?:png|jpg|svg))"', "".join(pages.values())))):
        src = REPO / rel
        assert src.is_file(), rel
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(rel)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", default=str(REPO / "1006-xhard12-env-plan.html"))
    ap.add_argument("--out", default=str(REPO / "artifacts" / "plan-site"))
    a = ap.parse_args()
    written = build(pathlib.Path(a.plan), pathlib.Path(a.out))
    pages = [w for w in written if w.endswith(".html")]
    print(f"PLAN_SITE=OK pages={len(pages)} images={len(written) - len(pages)} out={a.out}")


if __name__ == "__main__":
    main()
