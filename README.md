# video-to-gif

A lightweight, locally-hosted web service that converts video files to GIFs via drag-and-drop. Features a retro CRT/terminal aesthetic and runs on port 3000.

## Requirements

- Python 3.8+
- `ffmpeg` and `ffprobe` installed and on your `PATH`
- Flask 3.0+

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:3000` in your browser.

## Usage

**File:** Drag a video file onto the drop zone, or click to select one.

**URL:** Click the `[ URL ]` tab, paste any HTTP/HTTPS video URL, and press Enter or `[ CONVERT ]`. ffmpeg reads the URL directly — no intermediate download step. Works with S3, CDNs, direct links, and extensionless asset URLs.

Any format supported by ffmpeg works — MP4, MOV, MKV, WEBM, AVI, FLV, etc. The server validates input via `ffprobe`, not file extension.

## Output

Aspect ratio is always preserved. Orientation is auto-detected — portrait videos scale on height, landscape on width.

### Presets

| Preset | Resolution | FPS | Colors | Best for |
|--------|-----------|-----|--------|----------|
| EMBED  | 240px     | 10  | 64     | Docs, Slack, email — smallest file |
| WEB    | 360px     | 15  | 128    | Web pages, READMEs |
| FULL   | 480px     | 15  | 256    | Best quality (default) |

### Speed

1×, 2×, 4×, or 8× playback speed. Speeds up the GIF output while preserving the full video content — useful for long recordings. The status panel shows both the source duration and the resulting GIF duration after conversion.

- **Max upload size:** 500 MB
- **Quality:** two-pass conversion with palette generation for optimal color fidelity

## Project Structure

```
video_to_gif/
├── app.py               # Flask backend (routes, ffprobe validation, ffmpeg conversion)
├── templates/
│   └── index.html       # Frontend (retro CRT UI, embedded CSS + JS, no external deps)
└── requirements.txt     # Python dependencies (flask only)
```

## How It Works

**Backend (`app.py`):**
- `GET /` serves the UI
- `POST /convert` accepts `multipart/form-data` with fields: `video` (file) **or** `url` (HTTP/HTTPS string), plus `preset` (embed/web/full) and `speed` (1/2/4/8)
- URL inputs are passed directly to ffmpeg/ffprobe — no intermediate download
- `ffprobe` probes the file to confirm it contains a video stream and reads dimensions + duration
- Two-pass `ffmpeg` conversion: palette generation (`palettegen`) then GIF encode (`paletteuse`) for optimal color fidelity
- Speed-up applied via `setpts=PTS/{speed}` in the filter chain
- Uses `tempfile.TemporaryDirectory()` for automatic cleanup on success or error
- Returns the GIF as a file download with `X-Video-Duration` and `X-Video-Speed` headers, or JSON `{"error": "..."}` on failure

**Frontend (`templates/index.html`):**
- Vanilla JS, no external CDN dependencies
- Preset selector (EMBED / WEB / FULL) and speed selector (1× / 2× / 4× / 8×) with retro toggle buttons
- Drag-and-drop and file picker both feed the same `fetch('/convert')` handler
- ASCII spinner (`|/-\`) animates while the request is in-flight
- On success: displays source duration, GIF duration (after speed adjustment), and output file size
- On success, `URL.createObjectURL(blob)` offers the GIF for download without a second round-trip
- Errors from the server are displayed in amber in the status panel
