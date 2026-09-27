"""统计 6 局 mp4 的帧数、fps、时长。"""
import cv2, glob
ROOT = "artifacts/newtask-v4/v4-01/rollout/run1/episodes"
for env in ("PatternLock", "RouteStick"):
    for ep in (0, 3, 6):
        for p in sorted(glob.glob(f"{ROOT}/{env}_episode_{ep}/videos/*.mp4")):
            cap = cv2.VideoCapture(p)
            n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            # 实数帧
            cnt = 0
            while True:
                ok, _ = cap.read()
                if not ok: break
                cnt += 1
            print(f"{env} ep{ep}: meta_frames={n} decoded={cnt} fps={fps} size={w}x{h} dur_s={cnt/fps:.2f}")
