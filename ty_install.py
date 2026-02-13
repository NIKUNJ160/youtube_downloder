import yt_dlp
import os

url = input("Enter video link: ").strip()

if not url.startswith(("https://www.youtube.com/", "https://youtube.com/", "https://youtu.be/", "https://music.youtube.com/")):
    print("Error: Please enter a valid YouTube URL.")
    exit(1)

output_dir = os.path.join(os.path.expanduser("~"), "Downloads")

ffmpeg_path = os.path.join(
    os.path.expanduser("~"),
    r"AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
)

opts = {
    "ffmpeg_location": ffmpeg_path,
    "format": "bestvideo+bestaudio/best",
    "merge_output_format": "mp4",
    "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
    "progress_hooks": [lambda d: print(f"\r{d.get('_percent_str', '...')}", end="")
                        if d["status"] == "downloading" else None],
}

try:
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    print(f"\nDownload completed → {output_dir}")
except Exception as e:
    print(f"\nError: {e}")