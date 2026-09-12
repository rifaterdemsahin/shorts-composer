import json
import os
import tempfile
import pysrt

from moviepy import ImageClip, VideoFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx import MaskColor, Resize

import segmentation

DEFAULT_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def log(msg):
    print(f"[composer] {msg}", flush=True)


def load_subtitles(srt_path, video_duration, style_cfg, video_w, video_h):
    if not os.path.exists(srt_path):
        log(f"No subtitles file at {srt_path}, skipping captions.")
        return []

    subs = pysrt.open(srt_path)
    text_clips = []

    for sub in subs:
        start_sec = sub.start.ordinal / 1000.0
        end_sec = sub.end.ordinal / 1000.0

        if start_sec >= video_duration:
            continue

        txt_clip = (
            TextClip(
                font=style_cfg.get("font_path", DEFAULT_FONT),
                text=sub.text.replace("\n", " "),
                font_size=style_cfg.get("fontsize", 36),
                color=style_cfg.get("color", "yellow"),
                bg_color=style_cfg.get("bg_color", "black"),
                size=(int(video_w * 0.8), None),
                method="caption",
            )
            .with_start(start_sec)
            .with_end(min(end_sec, video_duration))
            .with_position(("center", int(video_h * 0.85)))
        )
        text_clips.append(txt_clip)

    log(f"Loaded {len(text_clips)} subtitle cues from {srt_path}.")
    return text_clips


def _build_via_segmentation(cfg):
    """Real background removal: MediaPipe selfie segmentation cuts the person out
    frame-by-frame and composites them over the background image (segmentation.py),
    then we reattach the original audio and burn subtitles in with moviepy."""
    fg_path = cfg["inputs"]["foreground_video"]
    bg_path = cfg["inputs"]["background_image"]
    pos_config = cfg["foreground_transform"]["position"]
    v_pos = pos_config[1] if isinstance(pos_config, list) else "bottom"

    tmp_silent = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    try:
        log("Running MediaPipe selfie segmentation + compositing over background...")
        segmentation.cutout_over_background(
            fg_path,
            bg_path,
            tmp_silent,
            scale=cfg["foreground_transform"]["scale"],
            position=v_pos,
        )

        log("Reattaching original audio...")
        composited = VideoFileClip(tmp_silent)
        original_audio = VideoFileClip(fg_path).audio
        composited = composited.with_audio(original_audio)

        sub_clips = load_subtitles(
            cfg["inputs"]["subtitles_file"], composited.duration, cfg["subtitle_style"], composited.w, composited.h
        )

        log("Burning in subtitles...")
        final_video = CompositeVideoClip([composited] + sub_clips, size=composited.size)

        output_path = cfg["output"]["filepath"]
        log(f"Encoding output video to {output_path} ...")
        final_video.write_videofile(
            output_path, fps=cfg["output"]["fps"], codec="libx264", audio_codec="aac", preset="ultrafast", threads=8
        )
        log("Encoding complete.")

        composited.close()
        final_video.close()
        return output_path
    finally:
        if os.path.exists(tmp_silent):
            os.remove(tmp_silent)


def _build_via_color_key(cfg):
    """Legacy path: RGB-distance chroma keying for real green/blue-screen footage."""
    log(f"Loading foreground video: {cfg['inputs']['foreground_video']}")
    fg_clip = VideoFileClip(cfg["inputs"]["foreground_video"])

    threshold = cfg["chroma_key"]["threshold"]
    if threshold > 0:
        log("Applying chroma key (MaskColor)...")
        keyed_fg = fg_clip.with_effects([
            MaskColor(
                color=tuple(cfg["chroma_key"]["key_color_rgb"]),
                threshold=threshold,
                stiffness=cfg["chroma_key"]["blur"],
            )
        ])
    else:
        log("Chroma key threshold is 0 — skipping keying, using opaque foreground inset.")
        keyed_fg = fg_clip

    pos_config = cfg["foreground_transform"]["position"]
    pos = tuple(pos_config) if isinstance(pos_config, list) else pos_config
    keyed_fg = keyed_fg.with_effects([Resize(cfg["foreground_transform"]["scale"])]).with_position(pos)

    log(f"Loading background image: {cfg['inputs']['background_image']}")
    bg_clip = (
        ImageClip(cfg["inputs"]["background_image"])
        .with_duration(fg_clip.duration)
        .with_effects([Resize(new_size=fg_clip.size)])
    )

    sub_clips = load_subtitles(
        cfg["inputs"]["subtitles_file"], fg_clip.duration, cfg["subtitle_style"], bg_clip.w, bg_clip.h
    )

    log("Compositing layers (background + chroma-keyed foreground + subtitles)...")
    final_video = CompositeVideoClip([bg_clip, keyed_fg] + sub_clips, size=bg_clip.size)

    output_path = cfg["output"]["filepath"]
    log(f"Encoding output video to {output_path} ...")
    final_video.write_videofile(
        output_path, fps=cfg["output"]["fps"], codec="libx264", audio_codec="aac", preset="ultrafast", threads=8
    )
    log("Encoding complete.")

    fg_clip.close()
    bg_clip.close()
    final_video.close()

    return output_path


def build_composition(config_path="config.json"):
    with open(config_path, "r") as f:
        cfg = json.load(f)

    method = cfg["chroma_key"].get("method", "color")
    if method == "segmentation":
        return _build_via_segmentation(cfg)
    return _build_via_color_key(cfg)


if __name__ == "__main__":
    build_composition()
