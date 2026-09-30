#!/usr/bin/env python3
"""v7 逐局对照站点服务（0929 站点方案 §5）：生成视频 vs SimpleMemVLA vs MME-VLA。

服务端完全复用同目录 ``v6_site.py`` 的媒体白名单与单段 Range 实现（``create_server``），只换页面
``v7_site.html`` 与站点目录。目录由 ``v7_site_catalog.py`` 生成。

    uv run --no-sync python scripts/injection-dev/site/v7_site.py --port 8070 --site-dir artifacts/newtask-v7/site
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("v6_site", HERE / "v6_site.py")
v6_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v6_site)

DEFAULT_SITE_DIR = v6_site.REPO_ROOT / "artifacts/newtask-v7/site"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8070)
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR)
    args = parser.parse_args()
    with v6_site.create_server(args.host, args.port, site_dir=args.site_dir,
                               html_path=HERE / "v7_site.html") as server:
        print(f"V7_SITE_READY host={args.host} port={server.server_port} videos={len(server.files.media)}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
