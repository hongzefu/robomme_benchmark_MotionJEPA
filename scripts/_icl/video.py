"""从已验证的原始 HDF5 导出观看视频，严格记录来源并支持补齐缺失产物。"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from robomme_icl.io.hdf5 import read_episode
from robomme_icl.io.paths import output_path, repository_root


FFMPEG = "/usr/bin/ffmpeg"
FFPROBE = "/usr/bin/ffprobe"
ENCODING = {"codec": "libx264", "pixel_format": "yuv420p", "crf": 18, "threads": 1,
            "layout": "base_rgb+wrist_rgb", "demonstration_border_rgb": [255, 0, 0],
            "demonstration_border_pixels": 6}


def _safe_output(path):
    """媒体路径必须位于仓库内，且不能写入官方只读参考集。"""
    target = output_path(path)
    reference = repository_root() / "data" / "robomme_data_h5"
    if target == reference or target.is_relative_to(reference):
        raise ValueError(f"禁止向官方参考数据写入媒体：{target}")
    return target


def _sha256(path):
    """以分块方式计算文件摘要，避免再次把完整媒体读入内存。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compose_frame(frame):
    """横拼原始 RGB，并且只在新数组上标出演示阶段的红框。"""
    images = [frame["observation"][name] for name in ("base_rgb", "wrist_rgb")]
    if any(not isinstance(image, np.ndarray) or image.dtype != np.uint8 or
           image.ndim != 3 or image.shape[2] != 3 for image in images):
        raise ValueError("视频只接受 uint8 的 H×W×3 原始 RGB")
    if images[0].shape[0] != images[1].shape[0]:
        raise ValueError("前视与腕部图像高度不同，禁止隐式缩放原始帧")
    merged = np.concatenate(images, axis=1)
    height, width = merged.shape[:2]
    if height <= 0 or width <= 0 or height % 2 or width % 2:
        raise ValueError("yuv420p 视频的宽高必须为正偶数")
    if bool(frame["info"]["is_demonstration"]):
        border = min(ENCODING["demonstration_border_pixels"], height // 2, width // 2)
        merged[:border] = merged[-border:] = (255, 0, 0)
        merged[:, :border] = merged[:, -border:] = (255, 0, 0)
    return merged


def _probe(path, *, frames, fps, width, height):
    """完整计数并解码视频，验证保存结果的帧数、帧率和分辨率。"""
    result = subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height,codec_name,pix_fmt,nb_read_frames,avg_frame_rate,r_frame_rate",
                             "-of", "json", str(path)], check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout).get("streams", [])
    if len(streams) != 1:
        raise ValueError("视频必须包含一条可读取的视频轨")
    stream = streams[0]
    actual = (int(stream["nb_read_frames"]), Fraction(stream["avg_frame_rate"]),
              int(stream["width"]), int(stream["height"]), stream["codec_name"], stream["pix_fmt"])
    expected = (frames, Fraction(str(fps)), width, height, "h264", "yuv420p")
    if actual != expected or Fraction(stream["r_frame_rate"]) != Fraction(str(fps)):
        raise ValueError(f"视频帧数、帧率、尺寸或编码不符：{actual} != {expected}")
    subprocess.run([FFMPEG, "-v", "error", "-xerror", "-threads", "1", "-i", str(path),
                    "-map", "0:v:0", "-threads", "1", "-f", "null", "-"],
                   check=True, capture_output=True)
    return {"frames": frames, "fps": fps, "width": width, "height": height, "decodable": True}


def _read_sidecar(path, identity):
    """已存在记录必须与本次输入和编码参数完全对应。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or any(value.get(key) != expected for key, expected in identity.items()):
        raise ValueError(f"视频来源或编码参数不匹配，禁止覆盖：{path}")
    if not isinstance(value.get("video_sha256"), str) or len(value["video_sha256"]) != 64:
        raise ValueError(f"视频来源记录缺少文件摘要：{path}")
    return value


def _verify_existing(video_path, metadata, identity):
    """摘要与完整解码均通过时才把已有 MP4 视为可复用产物。"""
    if _sha256(video_path) != metadata["video_sha256"]:
        raise ValueError(f"已有视频摘要不匹配，禁止覆盖：{video_path}")
    _probe(video_path, **{key: identity[key] for key in ("frames", "fps", "width", "height")})


def export_video(h5_path, video_path) -> dict:
    """验证 HDF5 后逐帧导出视频；失败不改 HDF5，恢复时只补齐缺失视频。"""
    source = output_path(h5_path)
    target = _safe_output(video_path)
    if target.suffix.lower() != ".mp4":
        raise ValueError("视频输出必须使用 .mp4 后缀")
    sidecar = _safe_output(target.with_suffix(".json"))
    record = read_episode(source)
    marker = next(frame for frame in record.frames if frame["info"].get("operation") == "reset_complete")
    fps = marker["info"]["native_runtime"]["control_freq"]
    frames = [frame for frame in record.frames if frame["info"].get("deliver_frame", False)]
    if not frames:
        raise ValueError("记录没有可交付的物理帧")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not np.isfinite(fps) or fps <= 0:
        raise ValueError("原版运行快照的control_freq必须为正数")
    first = compose_frame(frames[0])
    height, width = first.shape[:2]
    version = subprocess.run([FFMPEG, "-version"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    identity = {"source_content_hash": record.content_hash, "spec_hash": record.spec_hash,
                "source_operation_count": len(record.frames),
                "frames": len(frames), "fps": fps, "width": width, "height": height,
                "encoding": dict(ENCODING), "ffmpeg_version": version}
    metadata = _read_sidecar(sidecar, identity) if sidecar.exists() else None
    if target.exists():
        if metadata is None:
            raise FileExistsError(f"已有视频缺少来源记录，禁止覆盖：{target}")
        _verify_existing(target, metadata, identity)
        return {**metadata, "path": str(target), "sidecar": str(sidecar), "resumed": True}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths = []
    process = None
    try:
        # 唯一临时文件都在目标目录，发布使用排他硬链接，禁止覆盖任何现有文件。
        with tempfile.NamedTemporaryFile(prefix=f".{target.stem}-", suffix=".mp4", dir=target.parent, delete=False) as stream:
            temporary_video = Path(stream.name)
        temporary_paths.append(temporary_video)
        with tempfile.TemporaryFile(dir=target.parent) as errors:
            process = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                        "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
                                        "-framerate", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                                        "-pix_fmt", "yuv420p", "-crf", "18", "-threads", "1", "-movflags", "+faststart",
                                        str(temporary_video)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                for index, frame in enumerate(frames):
                    rgb = first if index == 0 else compose_frame(frame)
                    if rgb.shape != first.shape:
                        raise ValueError(f"视频帧 {index} 的分辨率与首帧不同")
                    process.stdin.write(memoryview(rgb).cast("B"))
                process.stdin.close()
                code = process.wait(timeout=120)
            except (BrokenPipeError, OSError) as exc:
                process.wait(timeout=120)
                errors.seek(0)
                raise RuntimeError(f"FFmpeg 编码失败：{errors.read().decode(errors='replace')}") from exc
            if code != 0:
                errors.seek(0)
                raise RuntimeError(f"FFmpeg 编码退出 {code}：{errors.read().decode(errors='replace')}")
        verification = _probe(temporary_video, frames=len(frames), fps=fps, width=width, height=height)
        result = {"schema_version": 1, **identity, "source_h5": str(source),
                  "video_sha256": _sha256(temporary_video), "verification": verification}
        if metadata is not None and metadata["video_sha256"] != result["video_sha256"]:
            raise ValueError("恢复编码与已保存的视频摘要不同，禁止改写来源记录")
        if metadata is None:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=f".{target.stem}-", suffix=".json",
                                             dir=target.parent, delete=False) as stream:
                temporary_json = Path(stream.name)
                temporary_paths.append(temporary_json)
                json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary_json, sidecar)
            except FileExistsError:
                concurrent = _read_sidecar(sidecar, identity)
                if concurrent["video_sha256"] != result["video_sha256"]:
                    raise ValueError("并发发布的视频摘要不同，拒绝覆盖")
        try:
            os.link(temporary_video, target)
        except FileExistsError:
            _verify_existing(target, result, identity)
        return {**result, "path": str(target), "sidecar": str(sidecar), "resumed": False}
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None and process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                # 编码进程提前退出时保留上面的原始错误，不被关闭管道的错误覆盖。
                pass
        for path in temporary_paths:
            path.unlink(missing_ok=True)
