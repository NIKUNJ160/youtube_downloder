# YouTube Downloader

A simple, fast, and ad-free YouTube downloader web app.

## Features

- 🎥 Download videos in 1080p, 720p, 480p
- 🎵 Extract high-quality audio (MP3)
- ⏸️ Pause and resume downloads
- 🚀 Real-time progress tracking
- 📱 Responsive design

## Tech Stack

- **Backend:** Python (Flask)
- **Frontend:** HTML, Tailwind CSS, JavaScript
- **Core:** yt-dlp, FFmpeg
- **Deployment:** Docker (Render / Railway / Fly.io)

## Deployment

### Render

1. Create a new **Web Service** on [Render](https://dashboard.render.com/).
2. Connect this repository.
3. Render will automatically detect `render.yaml` and deploy.

### Railway

1. New Project → Deploy from GitHub at [Railway](https://railway.app/).
2. Select this repository.
3. Railway will detect `railway.toml` and deploy.

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run app
python app.py
```
