import os
import pysrt
import whisper
import Levenshtein

_WHISPER_MODEL = None

def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = whisper.load_model("base")
    return _WHISPER_MODEL

def verify_pipeline(video_path, srt_path, truth_path):
    if not os.path.exists(video_path):
        return {"success": False, "error": "Video missing."}

    # 1. Load Ground Truth
    truth_text = ""
    if os.path.exists(truth_path):
        with open(truth_path, "r") as f:
            truth_text = f.read().strip().lower()

    # 2. Extract Audio & Transcribe
    result = get_whisper_model().transcribe(video_path)
    audio_text = result["text"].strip().lower()

    # 3. Parse SRT
    srt_text = ""
    if os.path.exists(srt_path):
        subs = pysrt.open(srt_path)
        srt_text = " ".join([sub.text.replace("\n", " ").strip() for sub in subs]).lower()

    # 4. Compare text distances
    def calc_match(source, target):
        if not source or not target: return 0.0
        dist = Levenshtein.distance(source, target)
        maxlen = max(len(source), len(target))
        return round((1 - (dist / maxlen)) * 100, 2)

    audio_to_truth = calc_match(truth_text, audio_text)
    srt_to_truth = calc_match(truth_text, srt_text)

    passed = audio_to_truth >= 85.0 and srt_to_truth >= 95.0

    return {
        "success": True,
        "passed": passed,
        "scores": {
            "actor_followed_script": audio_to_truth,
            "srt_matches_script": srt_to_truth
        },
        "texts": {
            "ground_truth": truth_text,
            "spoken_audio": audio_text,
            "srt_generated": srt_text
        }
    }
