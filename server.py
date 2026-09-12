import os
import json
import time
import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

import composer
from composer import build_composition
from verifier import verify_pipeline

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=1)

ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)
open(os.path.join(ASSETS_DIR, ".keep"), 'a').close()

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# ---- in-memory pipeline log/status, polled by the test page ----
STATE = {
    "stage": "idle",       # idle | rendering | verifying | done | error
    "logs": [],
    "output": None,
    "report": None,
    "error": None,
}


def push_log(message):
    STATE["logs"].append({"t": round(time.time(), 3), "message": message})
    print(message, flush=True)


def run_pipeline():
    STATE["stage"] = "rendering"
    STATE["logs"] = []
    STATE["output"] = None
    STATE["report"] = None
    STATE["error"] = None

    original_log = composer.log
    composer.log = push_log
    try:
        push_log("Pipeline started.")
        output_path = build_composition("config.json")
        STATE["output"] = output_path
        push_log(f"Render finished -> {output_path}")

        STATE["stage"] = "verifying"
        with open("config.json", "r") as f:
            cfg = json.load(f)
        push_log("Transcribing rendered audio with Whisper and comparing against script + SRT...")
        report = verify_pipeline(
            output_path,
            cfg["inputs"]["subtitles_file"],
            cfg["inputs"]["source_truth_txt"],
        )
        STATE["report"] = report
        push_log(f"Verification complete: passed={report.get('passed')} scores={report.get('scores')}")

        STATE["stage"] = "done"
    except Exception as e:
        STATE["stage"] = "error"
        STATE["error"] = str(e)
        push_log(f"ERROR: {e}")
        push_log(traceback.format_exc())
    finally:
        composer.log = original_log


class ConfigPayload(BaseModel):
    config: dict


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r") as f:
        return f.read()


@app.get("/test", response_class=HTMLResponse)
async def get_test_page():
    with open("test.html", "r") as f:
        return f.read()


@app.get("/updates", response_class=HTMLResponse)
async def get_updates_page():
    with open("updates.html", "r") as f:
        return f.read()


@app.get("/api/config")
async def get_config():
    with open("config.json", "r") as f:
        return json.load(f)


@app.post("/api/config")
async def update_config(payload: ConfigPayload):
    with open("config.json", "w") as f:
        json.dump(payload.config, f, indent=2)
    return {"status": "success"}


@app.post("/api/upload")
async def upload_asset(file: UploadFile = File(...)):
    with open(os.path.join(ASSETS_DIR, file.filename), "wb") as buffer:
        buffer.write(await file.read())
    return {"filename": file.filename}


@app.post("/api/run")
async def run_full_pipeline():
    """Kick off render + verify in the background thread and return immediately.
    Poll /api/status for live stage/logs."""
    if STATE["stage"] in ("rendering", "verifying"):
        raise HTTPException(status_code=409, detail="Pipeline already running.")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, run_pipeline)
    return {"status": "started"}


@app.get("/api/status")
async def get_status():
    return STATE


@app.post("/api/render")
async def render_video():
    loop = asyncio.get_event_loop()
    output_file = await loop.run_in_executor(executor, build_composition, "config.json")
    return {"output": output_file}


@app.post("/api/test-sync")
async def test_audio_subtitle_sync():
    loop = asyncio.get_event_loop()
    with open("config.json", "r") as f:
        cfg = json.load(f)

    report = await loop.run_in_executor(
        executor,
        verify_pipeline,
        cfg["output"]["filepath"],
        cfg["inputs"]["subtitles_file"],
        cfg["inputs"]["source_truth_txt"]
    )
    return report


@app.get("/output")
async def get_output_video():
    with open("config.json", "r") as f:
        cfg = json.load(f)
    return FileResponse(cfg["output"]["filepath"], media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
