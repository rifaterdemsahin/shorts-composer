import os
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from composer import build_composition
from verifier import verify_pipeline

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=1)

ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)
open(os.path.join(ASSETS_DIR, ".keep"), 'a').close()

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

class ConfigPayload(BaseModel):
    config: dict

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r") as f:
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
