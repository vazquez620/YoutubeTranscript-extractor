# YouTube Playlist Transcript Downloader

A full-stack web app that downloads transcripts for every video in a YouTube
playlist and bundles them into a ZIP file for easy download.

**No YouTube API key required.**

---

## Project structure

```
.
├── main.py                    # FastAPI backend
├── requirements.txt
├── README.md
├── static/
│   └── index.html             # Frontend (single HTML file, no framework)
└── yt_transcript_collector.py # Standalone CLI tool (see below)
```

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/vazquez620/youtubetranscript-extractor.git
cd youtubetranscript-extractor

# 2. (Optional) Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Run the web app

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000** in your browser.

Paste a public YouTube playlist URL and click **Download Transcripts**.
The server will collect all available transcripts and stream a ZIP file back
to your browser automatically.

---

## What's in the ZIP?

```
my_playlist_transcripts.zip
├── 001_intro_to_python.json
├── 002_functions_and_scope.json
├── 003_oop_basics.json
│   ...
└── skipped_videos.json        # summary of videos with no transcript
```

Each `{index}_{title}.json` file contains:

```json
{
  "video_id": "dQw4w9WgXcQ",
  "title": "Introduction to Python",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "language": "en",
  "transcript_text": "Hello and welcome to this tutorial ...",
  "transcript_segments": [
    { "start": 0.0, "duration": 3.5, "text": "Hello and welcome" },
    { "start": 3.5, "duration": 4.2, "text": "to this tutorial" }
  ]
}
```

`skipped_videos.json` summarises any videos that could not be transcribed
(disabled captions, unavailable video, etc.).

---

## Transcript language preference

1. Manually created English (`en`)
2. Auto-generated English (`en`)
3. Any other available language

---

## Standalone CLI tool

A command-line version is also included for offline / scripted use:

```bash
# Auto-named output file
python yt_transcript_collector.py "https://www.youtube.com/playlist?list=PLxxxxxx"

# Custom output file
python yt_transcript_collector.py "https://www.youtube.com/playlist?list=PLxxxxxx" output.json
```

---

## Notes

- Uses **yt-dlp** for playlist metadata extraction (no download, no API key).
- Uses **youtube-transcript-api** for transcript fetching (no API key).
- A 0.3 s delay is added between requests to reduce the chance of rate limiting.
- Blocking I/O is offloaded to a thread pool via `asyncio.run_in_executor` so
  the FastAPI event loop stays responsive.
- The ZIP is built entirely in memory (`io.BytesIO`) — nothing is written to disk.
