"""Real background removal for the foreground a-roll.

default-aroll.webm was shot against a plain brown wall, not a green screen, and
carries no alpha channel. A flat RGB-distance chroma key can't separate that
backdrop from skin tones (they overlap in color), so instead we run MediaPipe's
selfie segmentation model frame-by-frame to get a real person-shaped alpha mask,
then composite that cutout over the background image ourselves with OpenCV. The
result (silent, no subtitles yet) gets the original audio re-attached and
subtitles burned in afterwards by composer.py using moviepy.
"""
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL_PATH = "models/selfie_segmenter.tflite"


def log(msg):
    print(f"[segmentation] {msg}", flush=True)


def _make_segmenter():
    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.ImageSegmenterOptions(
        base_options=base_options,
        output_category_mask=False,
        output_confidence_masks=True,
    )
    return vision.ImageSegmenter.create_from_options(options)


def cutout_over_background(
    foreground_path,
    background_path,
    output_path,
    scale=0.8,
    position="bottom",
    mask_threshold=0.5,
    feather_px=6,
):
    """Segment the person out of `foreground_path` frame-by-frame and composite
    them over `background_path`, writing a silent video to `output_path`."""

    cap = cv2.VideoCapture(foreground_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open foreground video: {foreground_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    fg_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fg_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    bg_full = cv2.imread(background_path)
    if bg_full is None:
        raise RuntimeError(f"Could not open background image: {background_path}")

    out_w = int(fg_w / scale)
    out_h = int(fg_h / scale)
    bg_h, bg_w = bg_full.shape[:2]
    bg_scale = max(out_w / bg_w, out_h / bg_h)
    bg_resized = cv2.resize(bg_full, (int(bg_w * bg_scale) + 1, int(bg_h * bg_scale) + 1))
    bg_x = (bg_resized.shape[1] - out_w) // 2
    bg_y = (bg_resized.shape[0] - out_h) // 2
    bg_crop = bg_resized[bg_y:bg_y + out_h, bg_x:bg_x + out_w]

    fg_x = (out_w - fg_w) // 2
    fg_y = out_h - fg_h if position == "bottom" else (out_h - fg_h) // 2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

    segmenter = _make_segmenter()
    log(f"Segmenting {frame_count} frames at {fg_w}x{fg_h} -> compositing onto {out_w}x{out_h} canvas...")

    i = 0
    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = segmenter.segment(mp_image)
        mask = result.confidence_masks[0].numpy_view().squeeze()

        mask = np.clip((mask - mask_threshold) / max(1e-6, (1 - mask_threshold)), 0, 1)
        if feather_px > 0:
            k = feather_px * 2 + 1
            mask = cv2.GaussianBlur(mask, (k, k), 0)
        mask3 = mask[:, :, None]

        canvas = bg_crop.copy()
        roi = canvas[fg_y:fg_y + fg_h, fg_x:fg_x + fg_w].astype(np.float32)
        blended = roi * (1 - mask3) + frame_bgr.astype(np.float32) * mask3
        canvas[fg_y:fg_y + fg_h, fg_x:fg_x + fg_w] = blended.astype(np.uint8)

        writer.write(canvas)
        i += 1
        if i % 60 == 0:
            log(f"  segmented {i}/{frame_count} frames...")

    cap.release()
    writer.release()
    log(f"Wrote silent composited video -> {output_path}")
    return output_path, fps, (out_w, out_h)
