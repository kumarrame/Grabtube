# GrabTube 🎬

Free YouTube video & MP3 downloader. Fast, no signup required.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- ⚡ **MP4 Video Download** — 360p, 720p, 1080p quality options
- 🎵 **MP3 Audio Extraction** — 128, 192, 320 kbps
- 🔄 **3-Tier Fallback** — yt-dlp → Piped API → oEmbed for maximum uptime
- 📱 **Responsive UI** — Works on desktop and mobile
- 🌙 **Dark Theme** — Clean, modern interface
- 🚫 **No Signup** — Paste link and download

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask |
| Frontend | HTML, CSS, Vanilla JS |
| Video Extraction | yt-dlp, Piped API |
| Deployment | Gunicorn, Render.com |

## Quick Start

```bash
# Clone
git clone https://github.com/kumarrame/Grabtube.git
cd Grabtube

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

Open `http://localhost:5000` in your browser.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/info` | Fetch video metadata (title, thumbnail, formats) |
| `POST` | `/api/download` | Get download URL for selected format/quality |

### Example

```bash
# Get video info
curl -X POST http://localhost:5000/api/info \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Get download link
curl -X POST http://localhost:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "format": "mp4", "quality": "720p HD"}'
```

## Project Structure

```
Grabtube/
├── app.py                  # Flask backend + API routes
├── requirements.txt        # Python dependencies
├── render.yaml             # Render.com deployment config
├── static/
│   ├── css/style.css       # Dark theme styles
│   └── js/script.js        # Frontend logic
└── templates/
    ├── index.html           # Main page
    ├── about.html           # About page
    ├── contact.html         # Contact page
    ├── privacy.html         # Privacy policy
    └── terms.html           # Terms of service
```

## Deployment

### Render.com

Push to GitHub and connect repo on [render.com](https://render.com). The `render.yaml` handles config automatically.

### Manual (Gunicorn)

```bash
gunicorn app:app --bind 0.0.0.0:5000
```

## How It Works

1. User pastes a YouTube URL
2. Backend tries **yt-dlp** to extract video info & stream URLs
3. If yt-dlp fails, falls back to **Piped API** (multiple instances)
4. If Piped also fails, uses **YouTube oEmbed** for basic metadata
5. Download URL is returned directly — no server-side storage

## Disclaimer

For personal use only. Respect YouTube's Terms of Service.

## License

MIT
