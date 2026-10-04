"""逐局压缩视频核对（计划第二部分 1.7「视频路线表」、第四节「视频核对」）。

对一个结果目录逐局检查：

1. 输出键：每条结果行对应目录 ``<root>/<policy>[-<variant>]/<dataset>/<side>/<key>.a<attempt>/``（``side`` 取
   ``orig``／``new``）；最终行（``canary``／``infra``／``late`` 都不为真）的目录必须存在；该层下不对应任何结果行的
   目录记 ``orphan``，两条结果行指向同一目录记 ``duplicate``（两者合计为 ``key_mismatch``）。
2. 恰有一个 ``*.mp4``（0 个记 ``missing``，多于 1 个记 ``multi_mp4``）。
3. ``ffprobe`` 视频流编码为 ``h264``（否则 ``codec_bad``）。
4. 完整解码无错（``ffmpeg -v error -i <mp4> -map 0:v:0 -f null -``，退出码非 0 或 stderr 有内容记 ``decode_fail``），
   解码帧数即实际帧数。
5. 帧数符合路线公式（``frame_mismatch``）：``--frames-rule``
   - ``demo+exec``：期望 = 结果行 ``--demo-field``（默认 ``demo_frames``）+ ``--exec-field``（默认 ``exec_steps``）
     + ``--frame-offset``（默认 0）。新侧录像器与 ``demo_frames + exec_steps`` 的关系、GroundSG 原侧（演示帧 +
     已执行步数）、PonderPounce 原侧（``video_history`` 帧数 + 已执行步数，``--demo-field`` 指向记录它的字段）
     都用这条，偏移由预检实测后写进 ``launch.md`` 再固定传入；
   - ``field``：期望 = 结果行 ``--frames-field`` 的值（如 Astra 按其口径写入的帧数）；
   - ``fixed``：期望 = ``--expect-frames``；
   - ``none``：不核帧数（只用于预检第一局实测口径）。
6. 无残留原始帧（``raw_left``）：每局目录与 ``--raw-root`` 给出的额外目录（节点临时目录、NFS 同步根）下递归
   匹配 ``--raw-glob``（默认 ``*.raw *.mkv *.png *.jpg *.jpeg *.ppm``）的文件，以及名为 ``.spool`` 的目录。

判定行::

    VIDEO_SAVED=PASS|FAIL route=<路线> episodes=<n> missing=0 decode_fail=0 frame_mismatch=0 raw_left=0 bytes=<n>
        codec_bad=0 multi_mp4=0 key_mismatch=0

用法::

    python scripts/eval-official/video_check.py --route mmesg-oracle-new --root <结果根> --results <结果 jsonl>... \
        --side new [--policy-label mmesg-ground-sg-oracle] [--dataset test-hard0] \
        --frames-rule demo+exec --frame-offset 1 [--raw-root <节点临时目录>] [--out-json v.json]

测试里 ``FFTools`` 可替换为替身（非 slow 用例不调 ffmpeg）。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_RAW = ("*.raw", "*.mkv", "*.png", "*.jpg", "*.jpeg", "*.ppm")


class FFTools:
    """ffprobe／ffmpeg 封装；``codec`` 返回视频流编码名，``decode`` 返回 (是否无错, 解码帧数, 错误摘要)。"""

    def __init__(self, ffmpeg: str | None = None, ffprobe: str | None = None):
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        self.ffprobe = ffprobe or shutil.which("ffprobe")

    def codec(self, path: Path) -> str | None:
        if self.ffprobe:
            out = subprocess.run([self.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                  "stream=codec_name", "-of", "default=nw=1:nk=1", str(path)],
                                 capture_output=True, text=True, timeout=120)
            name = out.stdout.strip().splitlines()
            return name[0].strip() if out.returncode == 0 and name else None
        # 没有 ffprobe 时退回解析 ffmpeg -i 的流描述
        out = subprocess.run([self.ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=120)
        m = re.search(r"Video:\s*([A-Za-z0-9_]+)", out.stderr)
        return m.group(1) if m else None

    def decode(self, path: Path) -> tuple[bool, int | None, str]:
        out = subprocess.run([self.ffmpeg, "-v", "error", "-nostats", "-i", str(path), "-map", "0:v:0", "-f", "null",
                              "-", "-progress", "pipe:1"], capture_output=True, text=True, timeout=1800)
        frames = None
        for m in re.finditer(r"^frame=(\d+)", out.stdout, re.M):
            frames = int(m.group(1))
        err = out.stderr.strip()
        return out.returncode == 0 and not err, frames, err[:300]


def is_final(row: dict) -> bool:
    return not (row.get("canary") or row.get("infra") or row.get("late"))


def key_of(row: dict) -> str:
    if row.get("key"):
        return str(row["key"])
    ident = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    tier = row.get("tier") or ident.get("tier")
    return f"{row['task']}_{tier}_{int(row['seed'])}"


def label_of(row: dict) -> str:
    v = row.get("policy_variant")
    return f"{row['policy']}-{v}" if v else str(row["policy"])


def expected_frames(row: dict, args) -> int | None:
    rule = args.frames_rule
    if rule == "none":
        return None
    if rule == "fixed":
        return int(args.expect_frames)
    if rule == "field":
        v = row.get(args.frames_field)
        return None if v is None else int(v)
    d, e = row.get(args.demo_field), row.get(args.exec_field)
    if d is None or e is None:
        return -1  # 缺字段：无法算期望，按不符计
    return int(d) + int(e) + int(args.frame_offset)


def raw_files(d: Path, globs: tuple[str, ...]) -> list[Path]:
    if not d.exists():
        return []
    hits = {p for g in globs for p in d.rglob(g)}
    hits |= {p for p in d.rglob(".spool") if p.is_dir()}
    return sorted(hits)


def check(rows: list[dict], root: Path, args, tools: FFTools) -> dict:
    side = args.side
    counts = dict(episodes=0, missing=0, decode_fail=0, frame_mismatch=0, raw_left=0, bytes=0, codec_bad=0,
                  multi_mp4=0, orphan=0, duplicate=0)
    per: list[dict] = []
    claimed: dict[Path, int] = {}
    parents: set[Path] = set()
    for r in rows:
        if r.get("canary"):
            continue
        label = args.policy_label or label_of(r)
        ds = args.dataset or r.get("dataset")
        d = root / label / str(ds) / side / f"{key_of(r)}.a{int(r.get('attempt') or 1)}"
        parents.add(d.parent)
        claimed[d] = claimed.get(d, 0) + 1
        if not is_final(r):
            continue
        counts["episodes"] += 1
        item = {"dir": str(d), "status": r.get("status")}
        mp4s = sorted(d.glob("*.mp4")) if d.is_dir() else []
        if not mp4s:
            counts["missing"] += 1
            item["problem"] = "missing"
            per.append(item)
            continue
        if len(mp4s) > 1:
            counts["multi_mp4"] += 1
            item["problem"] = "multi_mp4"
        mp4 = mp4s[0]
        counts["bytes"] += mp4.stat().st_size
        codec = tools.codec(mp4)
        if codec != "h264":
            counts["codec_bad"] += 1
        ok, frames, err = tools.decode(mp4)
        if not ok:
            counts["decode_fail"] += 1
        exp = expected_frames(r, args)
        if exp is not None and frames != exp:
            counts["frame_mismatch"] += 1
        raws = raw_files(d, tuple(args.raw_glob))
        counts["raw_left"] += len(raws)
        item.update(mp4=str(mp4), codec=codec, decode_ok=ok, frames=frames, expected_frames=exp, error=err or None,
                    raw_left=[str(p) for p in raws], bytes=mp4.stat().st_size)
        per.append(item)
    counts["duplicate"] = sum(1 for v in claimed.values() if v > 1)
    for par in parents:
        if par.is_dir():
            counts["orphan"] += sum(1 for c in par.iterdir() if c.is_dir() and c not in claimed)
    for extra in args.raw_root or []:
        counts["raw_left"] += len(raw_files(Path(extra), tuple(args.raw_glob)))
    counts["key_mismatch"] = counts["orphan"] + counts["duplicate"]
    bad = any(counts[k] for k in ("missing", "decode_fail", "frame_mismatch", "raw_left", "codec_bad", "multi_mp4",
                                  "key_mismatch"))
    counts["verdict"] = "FAIL" if bad or counts["episodes"] == 0 else "PASS"
    return {"summary": counts, "episodes": per}


def verdict_line(res: dict, route: str) -> str:
    c = res["summary"]
    return (f"VIDEO_SAVED={c['verdict']} route={route} episodes={c['episodes']} missing={c['missing']} "
            f"decode_fail={c['decode_fail']} frame_mismatch={c['frame_mismatch']} raw_left={c['raw_left']} "
            f"bytes={c['bytes']} codec_bad={c['codec_bad']} multi_mp4={c['multi_mp4']} key_mismatch={c['key_mismatch']}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="逐局压缩视频核对")
    ap.add_argument("--route", required=True)
    ap.add_argument("--root", required=True, help="结果根（其下为 <policy>[-<variant>]/<dataset>/<side>/<key>.a<attempt>/）")
    ap.add_argument("--results", nargs="+", required=True)
    ap.add_argument("--side", choices=["orig", "new"], required=True)
    ap.add_argument("--policy-label", default=None, help="覆盖 <policy>[-<variant>]（默认由结果行 policy、policy_variant 拼）")
    ap.add_argument("--dataset", default=None, help="覆盖结果行 dataset")
    ap.add_argument("--frames-rule", choices=["demo+exec", "field", "fixed", "none"], default="demo+exec")
    ap.add_argument("--demo-field", default="demo_frames")
    ap.add_argument("--exec-field", default="exec_steps")
    ap.add_argument("--frame-offset", type=int, default=0)
    ap.add_argument("--frames-field", default="video_frames")
    ap.add_argument("--expect-frames", type=int, default=None)
    ap.add_argument("--raw-glob", nargs="*", default=list(DEFAULT_RAW))
    ap.add_argument("--raw-root", action="append", default=[])
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--ffprobe", default=None)
    ap.add_argument("--out-json", default=None)
    return ap


def main(argv: list[str] | None = None, *, tools: FFTools | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.frames_rule == "fixed" and args.expect_frames is None:
        raise SystemExit("--frames-rule fixed 需要 --expect-frames")
    rows: list[dict] = []
    for p in args.results:
        rows += [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
    res = check(rows, Path(args.root), args, tools or FFTools(args.ffmpeg, args.ffprobe))
    line = verdict_line(res, args.route)
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps({**res, "line": line}, ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8")
    print(line, flush=True)
    return 0 if res["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
