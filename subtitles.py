"""Whisper-timed subtitle generation.

Transcribes the foreground video with word-level timestamps and groups the
words into short caption lines using their real spoken timing (rather than
Whisper's coarser sentence-level segments), so captions land in sync with
what's actually being said.
"""
import os
import traceback
import whisper

_MODEL = None


def log(msg):
    print(f"[subtitles] {msg}", flush=True)


def get_model():
    global _MODEL
    if _MODEL is None:
        log("Loading Whisper model (base)...")
        _MODEL = whisper.load_model("base")
    return _MODEL


def _format_ts(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def needs_regeneration(foreground_path, srt_path):
    """Returns (needs, reason)."""
    if not os.path.exists(srt_path):
        return True, f"no subtitles file found at {srt_path}"
    if not os.path.exists(foreground_path):
        return False, ""
    if os.path.getmtime(foreground_path) > os.path.getmtime(srt_path):
        return True, f"{foreground_path} is newer than {srt_path} (source video changed since captions were made)"
    return False, ""


def generate(foreground_path, srt_path, script_path, words_per_line=7):
    log(f"Transcribing {foreground_path} with Whisper (word-level timestamps)...")
    model = get_model()
    result = model.transcribe(foreground_path, word_timestamps=True, verbose=False)

    words = [w for seg in result["segments"] for w in seg.get("words", [])]
    if not words:
        raise RuntimeError("Whisper returned no word-level timestamps for this video.")

    lines = []
    for i in range(0, len(words), words_per_line):
        chunk = words[i:i + words_per_line]
        text = "".join(w["word"] for w in chunk).strip()
        lines.append({"start": float(chunk[0]["start"]), "end": float(chunk[-1]["end"]), "text": text})

    with open(srt_path, "w") as f:
        for idx, line in enumerate(lines, start=1):
            f.write(f"{idx}\n")
            f.write(f"{_format_ts(line['start'])} --> {_format_ts(line['end'])}\n")
            f.write(line["text"] + "\n\n")

    with open(script_path, "w") as f:
        f.write(result["text"].strip() + "\n")

    log(f"Wrote {len(lines)} Whisper-timed caption lines ({len(words)} words) -> {srt_path}")
    log(f"Wrote ground-truth script -> {script_path}")
    return len(lines)


def ensure_subtitles(cfg, force=False):
    """Regenerate subtitles.srt/script.txt with Whisper if they're missing or
    stale relative to the foreground video. Non-fatal: logs and returns False
    on failure instead of raising, so a transcription error doesn't take down
    the whole render."""
    fg = cfg["inputs"]["foreground_video"]
    srt = cfg["inputs"]["subtitles_file"]
    script = cfg["inputs"]["source_truth_txt"]

    needs, reason = needs_regeneration(fg, srt)
    if force:
        needs, reason = True, "regeneration explicitly requested"

    if not needs:
        log(f"Existing subtitles at {srt} are already in sync with {fg} — skipping Whisper transcription.")
        return False

    log(f"New subtitles needed: {reason}.")
    log("Generating fresh captions with Whisper...")
    try:
        generate(fg, srt, script)
        return True
    except Exception as e:
        log(f"ERROR: Whisper subtitle generation failed: {e}")
        log(traceback.format_exc())
        if os.path.exists(srt):
            log(f"Falling back to existing {srt} (may be out of sync with the video).")
        else:
            log("No existing subtitles to fall back to — the video will render without captions.")
        return False
