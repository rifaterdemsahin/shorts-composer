# shorts-composer

Compose short videos from background subtitles and chrome keyed footage.

Repo: https://github.com/rifaterdemsahin/shorts-composer/tree/main
GitHub Pages: https://rifaterdemsahin.github.io/shorts-composer/

A macOS Apple Silicon native video compositing API designed for AI agents. It handles background replacement, chroma-keying, subtitle burn-in, and verification against ground-truth scripts.

## Pipeline

![pipeline](assets/pipeline.svg)

## Setup on macOS (M1/M2/M3)

1. **Install System Dependencies**
   ```bash
   brew install ffmpeg imagemagick
   sed -i '' 'r /<policy domain="coder" rights="none" pattern="LABEL" \/>/d' /opt/homebrew/etc/ImageMagick-7/policy.xml
   ```

2. **Initialize Repository**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   gh repo create ai-short-composer --public --source=. --remote=origin --push
   ```

3. **Install Python Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Run the Server**
   ```bash
   python server.py
   ```

Access the dashboard at `http://localhost:8000`.
