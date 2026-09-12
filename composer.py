import json
import os
import pysrt
from moviepy.config import change_settings
# macOS M1 ImageMagick patch
change_settings({"IMAGEMAGICK_BINARY": "/opt/homebrew/bin/magick"})

from moviepy.editor import ImageClip, VideoFileClip, TextClip, CompositeVideoClip
import moviepy.video.fx.all as vfx

def load_subtitles(srt_path, video_duration, style_cfg, video_w, video_h):
    if not os.path.exists(srt_path):
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
                sub.text.replace("\n", " "),
                fontsize=style_cfg.get("fontsize", 36),
                color=style_cfg.get("color", "yellow"),
                bg_color=style_cfg.get("bg_color", "black"),
                size=(int(video_w * 0.8), None),
                method="caption"
            )
            .set_start(start_sec)
            .set_end(min(end_sec, video_duration))
            .set_position(('center', int(video_h * 0.85)))
        )
        text_clips.append(txt_clip)

    return text_clips

def build_composition(config_path="config.json"):
    with open(config_path, "r") as f:
        cfg = json.load(f)

    fg_clip = VideoFileClip(cfg["inputs"]["foreground_video"])
    keyed_fg = vfx.mask_color(
        fg_clip,
        color=cfg["chroma_key"]["key_color_rgb"],
        thr=cfg["chroma_key"]["threshold"],
        s=cfg["chroma_key"]["blur"]
    )

    pos_config = cfg["foreground_transform"]["position"]
    pos = (pos_config[0], pos_config[1]) if isinstance(pos_config, list) else pos_config
    keyed_fg = keyed_fg.resize(cfg["foreground_transform"]["scale"]).set_position(pos)

    bg_clip = ImageClip(cfg["inputs"]["background_image"]).set_duration(fg_clip.duration).resize(newsize=fg_clip.size)

    sub_clips = load_subtitles(cfg["inputs"]["subtitles_file"], fg_clip.duration, cfg["subtitle_style"], bg_clip.w, bg_clip.h)

    final_video = CompositeVideoClip([bg_clip, keyed_fg] + sub_clips, size=bg_clip.size)

    output_path = cfg["output"]["filepath"]
    final_video.write_videofile(
        output_path, fps=cfg["output"]["fps"], codec="libx264", audio_codec="aac", preset="ultrafast", threads=8
    )

    fg_clip.close()
    bg_clip.close()
    final_video.close()

    return output_path

if __name__ == "__main__":
    build_composition()
