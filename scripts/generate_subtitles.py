"""One-off helper: transcribe assets/default-aroll.webm with Whisper and
write assets/subtitles.srt + assets/script.txt (ground truth) from the result."""
import whisper

def format_ts(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def main():
    model = whisper.load_model("base")
    result = model.transcribe("assets/default-aroll.webm", verbose=False)

    with open("assets/subtitles.srt", "w") as f:
        for i, seg in enumerate(result["segments"], start=1):
            f.write(f"{i}\n")
            f.write(f"{format_ts(seg['start'])} --> {format_ts(seg['end'])}\n")
            f.write(seg["text"].strip() + "\n\n")

    with open("assets/script.txt", "w") as f:
        f.write(result["text"].strip() + "\n")

    print("Wrote assets/subtitles.srt and assets/script.txt")

if __name__ == "__main__":
    main()
