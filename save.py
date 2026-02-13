import yt_dlp
import os
import sys
import json
import uuid
import time
import threading
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

# In-memory job store
jobs = {}


def make_progress_hook(job_id, video_index):
    """Create a progress hook bound to a specific job and video index."""
    def hook(d):
        job = jobs.get(job_id)
        if not job:
            return

        if video_index >= len(job['videos']):
            return

        vid = job['videos'][video_index]

        if d['status'] == 'downloading':
            vid['status'] = 'downloading'
            vid['percent'] = d.get('_percent_str', '0%').strip()
            vid['speed'] = d.get('_speed_str', '-')
            vid['eta'] = d.get('_eta_str', '-')
            raw = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            vid['raw_percent'] = round((raw / total) * 100, 1)

        elif d['status'] == 'finished':
            vid['status'] = 'merging'
            vid['percent'] = '100%'
            vid['raw_percent'] = 100

        elif d['status'] == 'error':
            vid['status'] = 'error'

    return hook


def run_download(job_id, url, output_dir, quality):
    """Run the download in a background thread with pause/resume support."""
    job = jobs[job_id]

    format_map = {
        'best':  'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '1080':  'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
        '720':   'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
        '480':   'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
        'audio': 'bestaudio[ext=m4a]/bestaudio',
    }

    os.makedirs(output_dir, exist_ok=True)

    postprocessors = []
    if quality == 'audio':
        postprocessors = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }]
    else:
        postprocessors = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }]

    # Download each video individually for fine-grained progress tracking
    for i, vid in enumerate(job['videos']):
        if job.get('cancelled'):
            break

        # ── Pause/resume: wait here if paused ──
        while job.get('paused') and not job.get('cancelled'):
            vid['status'] = 'paused'
            job['resume_event'].wait(timeout=0.5)

        if job.get('cancelled'):
            break

        vid['status'] = 'downloading'
        video_url = vid.get('url')
        if not video_url:
            vid['status'] = 'error'
            vid['error'] = 'No URL available'
            continue

        ydl_opts = {
            'format': format_map.get(quality, format_map['best']),
            'outtmpl': os.path.join(output_dir, f"{i+1:03d} - %(title)s.%(ext)s"),
            'merge_output_format': 'mp4' if quality != 'audio' else None,
            'progress_hooks': [make_progress_hook(job_id, i)],
            'postprocessors': postprocessors,
            'nooverwrites': True,
            'continuedl': True,  # resume partial downloads
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            vid['status'] = 'done'
            vid['raw_percent'] = 100
        except Exception as e:
            vid['status'] = 'error'
            vid['error'] = str(e)

    job['status'] = 'done'


# ──────────────── Routes ────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/info', methods=['POST'])
def fetch_info():
    """Fetch video/playlist metadata without downloading."""
    data = request.get_json()
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return jsonify({'error': 'Could not extract info'}), 400

        # Check if it's a single video or a playlist
        is_playlist = info.get('_type') == 'playlist' or 'entries' in info

        if is_playlist:
            entries = list(info.get('entries', []))
            videos = []
            for e in entries:
                if e:
                    videos.append({
                        'title': e.get('title', 'Unknown'),
                        'url': e.get('url') or e.get('webpage_url') or f"https://www.youtube.com/watch?v={e.get('id', '')}",
                        'duration': e.get('duration'),
                        'thumbnail': e.get('thumbnails', [{}])[-1].get('url') if e.get('thumbnails') else None,
                    })
            return jsonify({
                'type': 'playlist',
                'title': info.get('title', 'Unknown Playlist'),
                'thumbnail': info.get('thumbnails', [{}])[-1].get('url') if info.get('thumbnails') else None,
                'video_count': len(videos),
                'videos': videos,
            })
        else:
            # Single video
            thumb = None
            thumbs = info.get('thumbnails', [])
            if thumbs:
                thumb = thumbs[-1].get('url')
            return jsonify({
                'type': 'video',
                'title': info.get('title', 'Unknown Video'),
                'thumbnail': thumb,
                'video_count': 1,
                'videos': [{
                    'title': info.get('title', 'Unknown Video'),
                    'url': info.get('webpage_url') or url,
                    'duration': info.get('duration'),
                    'thumbnail': thumb,
                }],
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
def start_download():
    """Start a background download job."""
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', 'best')
    output_dir = data.get('output', 'downloads')
    videos = data.get('videos', [])

    if not url or not videos:
        return jsonify({'error': 'URL and video list required'}), 400

    job_id = str(uuid.uuid4())[:8]
    resume_event = threading.Event()
    resume_event.set()  # start in "not paused" state

    job_videos = []
    for v in videos:
        job_videos.append({
            'title': v.get('title', 'Unknown'),
            'url': v.get('url', ''),
            'status': 'queued',
            'percent': '0%',
            'raw_percent': 0,
            'speed': '-',
            'eta': '-',
            'error': None,
        })

    jobs[job_id] = {
        'status': 'running',
        'paused': False,
        'resume_event': resume_event,
        'videos': job_videos,
    }

    thread = threading.Thread(target=run_download, args=(job_id, url, output_dir, quality), daemon=True)
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/api/pause/<job_id>', methods=['POST'])
def pause_job(job_id):
    """Pause a running download job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    job['paused'] = True
    job['resume_event'].clear()
    job['status'] = 'paused'
    return jsonify({'ok': True, 'status': 'paused'})


@app.route('/api/resume/<job_id>', methods=['POST'])
def resume_job(job_id):
    """Resume a paused download job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    job['paused'] = False
    job['resume_event'].set()
    job['status'] = 'running'
    # Mark paused videos back to queued
    for v in job['videos']:
        if v['status'] == 'paused':
            v['status'] = 'queued'
    return jsonify({'ok': True, 'status': 'running'})


@app.route('/api/progress/<job_id>')
def progress(job_id):
    """SSE endpoint for real-time progress."""
    def generate():
        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            payload = {
                'status': job['status'],
                'paused': job.get('paused', False),
                'videos': [
                    {k: v for k, v in vid.items()}
                    for vid in job['videos']
                ],
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if job['status'] == 'done':
                break
            time.sleep(0.8)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


if __name__ == '__main__':
    print("\n  🌐  YouTube Downloader")
    print("  🔗  http://localhost:5000\n")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
