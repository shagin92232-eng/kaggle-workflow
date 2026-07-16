"""Landscape → 9:16 vertical reframe with MediaPipe face tracking.

Detects the dominant face per sampled frame, smooths the crop-window path,
and renders the crop with FFmpeg. Falls back to a static center crop when
no face is found (or MediaPipe is unavailable).

Face detection here is ONLY used to decide where to crop — faces are never
modified.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from utils.ffmpeg_utils import run_ffmpeg, video_dimensions
from utils.logger import get_logger

log = get_logger(__name__)

OUT_W, OUT_H = 1080, 1920
_SAMPLE_EVERY_S = 0.5  # face-detect twice per second, interpolate between


def _detect_face_centers(video: Path) -> list[tuple[float, float]] | None:
    """Sample frames, return [(t_seconds, face_center_x_fraction)]. None if no faces."""
    try:
        import cv2
        import mediapipe as mp
    except ImportError as exc:
        log.warning(f"MediaPipe/OpenCV unavailable ({exc}) — using center crop")
        return None

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(fps * _SAMPLE_EVERY_S))

    centers: list[tuple[float, float]] = []
    with mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    ) as detector:
        frame_idx = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if frame_idx % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.process(rgb)
                if result.detections:
                    # largest face wins
                    best = max(
                        result.detections,
                        key=lambda d: d.location_data.relative_bounding_box.width
                        * d.location_data.relative_bounding_box.height,
                    )
                    box = best.location_data.relative_bounding_box
                    cx = box.xmin + box.width / 2
                    centers.append((frame_idx / fps, min(max(cx, 0.0), 1.0)))
            frame_idx += 1
    cap.release()
    return centers or None


def _smooth(centers: list[tuple[float, float]], alpha: float = 0.25) -> list[tuple[float, float]]:
    """Exponential smoothing to avoid jittery crop movement."""
    smoothed = []
    prev = centers[0][1]
    for t, x in centers:
        prev = prev + alpha * (x - prev)
        smoothed.append((t, prev))
    return smoothed


async def reframe_vertical(source: Path, dest: Path) -> Path:
    """Crop `source` to 9:16 following the face; center crop as fallback."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    w, h = video_dimensions(source)
    crop_w = int(h * 9 / 16)

    if crop_w >= w:
        # Already vertical/square — just scale+pad to 1080x1920
        vf = (
            f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
            f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2"
        )
        args = ["-i", str(source), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-c:a", "copy", str(dest)]
        await asyncio.to_thread(run_ffmpeg, args, "reframe-pad")
        return dest

    centers = await asyncio.to_thread(_detect_face_centers, source)

    if not centers:
        x_expr = f"{(w - crop_w) // 2}"
        log.info("No face detected — using static center crop")
    else:
        centers = _smooth(centers)
        # Build a piecewise-linear x(t) expression for FFmpeg crop filter
        # Cap the number of keypoints to keep the filter string manageable.
        max_pts = 60
        if len(centers) > max_pts:
            stride = len(centers) / max_pts
            centers = [centers[int(i * stride)] for i in range(max_pts)]
        expr = None
        for (t0, c0), (t1, c1) in zip(centers, centers[1:]):
            x0 = max(0, min(w - crop_w, int(c0 * w - crop_w / 2)))
            x1 = max(0, min(w - crop_w, int(c1 * w - crop_w / 2)))
            dt = max(t1 - t0, 1e-3)
            seg = f"({x0}+({x1}-{x0})*(t-{t0:.2f})/{dt:.2f})"
            expr = seg if expr is None else f"if(lt(t,{t0:.2f}),{expr},{seg})"
        last_x = max(0, min(w - crop_w, int(centers[-1][1] * w - crop_w / 2)))
        x_expr = f"if(gte(t,{centers[-1][0]:.2f}),{last_x},{expr})" if expr else str(last_x)

    vf = f"crop={crop_w}:{h}:x='{x_expr}':y=0,scale={OUT_W}:{OUT_H}"
    args = ["-i", str(source), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-c:a", "copy", str(dest)]
    await asyncio.to_thread(run_ffmpeg, args, "reframe-facetrack")
    return dest
