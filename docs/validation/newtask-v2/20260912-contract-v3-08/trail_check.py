"""白球尾迹减半核验：比较两次运行同一条 RouteStick episode 视频里白色像素的「最长连续白帧游程」。

原理：同一冻结规格、同一 seed 下两次运行的机械臂轨迹逐帧相同（08 与 07 逐条 timestep 数一致），
画面唯一差异是桌面白球尾迹的存活步数（``RouteStick.step`` 里 ``highlight_position`` 的
``end_step`` 40→20）。一颗球盖住某像素的时长 = 存活步数 + 后续相邻球重叠带来的延长量 E；
两次运行的运动完全一样，E 逐像素相同，所以「该像素最长连续白帧游程」之差 run07 − run08
在尾迹像素上应恰为两侧存活步数之差（``--expected-diff``，08 对 07 是 20，09 对 07 是 30、09 对 08 是 10），在机械臂等非尾迹像素上为 0。这比像素面积比值干净——Panda 机械臂本身
是白色的，面积法分母会被它污染（实测面积比 0.733 而非 0.5）。

做法：逐帧取三通道均 ≥ ``WHITE_THRESHOLD`` 的像素为「白」，剔除首帧就是白的静态像素（靶盘白环、
文字），对每个像素算最长连续白帧游程；取 run07 ≥ ``MIN_RUN_LEFT`` 且 run07 − run08 > 0 的像素
（只有尾迹像素会有正差），看差值的中位数与落在 期望值 ±2 的占比。

判定行：``TRAIL_HALVED=PASS|FAIL expected=<期望差> median_diff=<中位数> share_pm2=<占比> n=<像素数> left_frames=<帧数> right_frames=<帧数> left=<run> right=<run>``，
PASS 条件：n ≥ 100、中位数在 期望值 ±2 内、占比 ≥ 0.4、两侧帧数相同。

用法（仓库根目录）::

    uv run --no-sync python docs/validation/newtask-v2/20260912-contract-v3-08/trail_check.py \
        --left 20260911-contract-v3-07 --left-mode P01x20 \
        --right 20260912-contract-v3-08 --right-mode P01x10 \
        --difficulty easy --episode 0 --out docs/validation/newtask-v2/20260912-contract-v3-08/trail_check_easy.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
WHITE_THRESHOLD = 170  # 球体有明暗，230 只抓到高光；170 实测把尾迹像素从 41 个放大到 458 个而机械臂差值仍为 0
MIN_RUN_LEFT = 30  # 参考侧（07，存活 40 步）游程至少 30 帧：短于存活步数的像素多半是机械臂扫过，不是尾迹；参考侧换 08 时用 --min-run-left 15
MIN_PIXELS = 100
EXPECTED_DIFF = 20
MEDIAN_TOLERANCE = 2
MIN_SHARE = 0.4


def _find_video(run_id: str, mode: str, difficulty: str, episode: int) -> Path:
    videos = REPO_ROOT / "artifacts" / "injection" / run_id / "feasibility" / mode / "RouteStick" / difficulty / "videos"
    matches = sorted(videos.glob(f"RouteStick_ep{episode}_seed*_{difficulty}_*.mp4"))
    if len(matches) != 1:
        raise SystemExit(f"{videos} 下 ep{episode} 的视频应恰有 1 个，实际 {len(matches)}")
    return matches[0]


def _longest_white_runs(path: Path) -> tuple[np.ndarray, int]:
    """返回（每像素最长连续白帧游程，帧数）；首帧就是白的像素整段剔除。"""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"打不开视频：{path}")
    best = cur = base = None
    frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        white = np.all(frame >= WHITE_THRESHOLD, axis=2)
        if base is None:
            base = white.copy()
            best = np.zeros(white.shape, dtype=np.int32)
            cur = np.zeros(white.shape, dtype=np.int32)
        white &= ~base
        cur = np.where(white, cur + 1, 0)
        best = np.maximum(best, cur)
        frames += 1
    cap.release()
    if frames == 0:
        raise SystemExit(f"视频没有帧：{path}")
    return best, frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--left", required=True, help="参考侧 run id（尾迹 40 步）")
    parser.add_argument("--left-mode", required=True, help="参考侧档目录名，如 P01x20")
    parser.add_argument("--right", required=True, help="候选侧 run id（尾迹 20 步）")
    parser.add_argument("--right-mode", required=True, help="候选侧档目录名，如 P01x10")
    parser.add_argument("--difficulty", default="easy")
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument("--out", default=None, help="把差值直方图与结论写到该 JSON")
    parser.add_argument("--expected-diff", type=int, default=EXPECTED_DIFF, help="两侧存活步数之差（默认 20：08 对 07）")
    parser.add_argument("--min-run-left", type=int, default=MIN_RUN_LEFT, help="参考侧游程下限（默认 30；参考侧是 08 时用 15）")
    args = parser.parse_args()

    left_video = _find_video(args.left, args.left_mode, args.difficulty, args.episode)
    right_video = _find_video(args.right, args.right_mode, args.difficulty, args.episode)
    left, left_frames = _longest_white_runs(left_video)
    right, right_frames = _longest_white_runs(right_video)
    diff = left - right
    lo, hi = args.expected_diff - MEDIAN_TOLERANCE, args.expected_diff + MEDIAN_TOLERANCE
    trail = (left >= args.min_run_left) & (diff > 0)
    values = diff[trail]
    n = int(values.size)
    median = float(np.median(values)) if n else float("nan")
    share = float(np.mean((values >= lo) & (values <= hi))) if n else 0.0
    passed = (
        n >= MIN_PIXELS and lo <= median <= hi
        and share >= MIN_SHARE and left_frames == right_frames
    )
    line = (
        f"TRAIL_HALVED={'PASS' if passed else 'FAIL'} expected={args.expected_diff} median_diff={median:.1f} share_pm2={share:.3f} n={n} "
        f"left_frames={left_frames} right_frames={right_frames} difficulty={args.difficulty} episode={args.episode} "
        f"left={args.left} right={args.right}"
    )
    print(line)
    if args.out:
        histogram = {str(k): int(v) for k, v in zip(*np.unique(values, return_counts=True))} if n else {}
        Path(args.out).write_text(json.dumps({
            "verdict_line": line, "passed": passed, "expected_diff": args.expected_diff, "median_diff": median, "share_pm2": share, "n_trail_pixels": n,
            "left_frames": left_frames, "right_frames": right_frames,
            "white_threshold": WHITE_THRESHOLD, "min_run_left": args.min_run_left, "min_pixels": MIN_PIXELS,
            "median_range": [lo, hi], "min_share": MIN_SHARE,
            "left_video": str(left_video.relative_to(REPO_ROOT)), "right_video": str(right_video.relative_to(REPO_ROOT)),
            "diff_histogram": histogram,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
