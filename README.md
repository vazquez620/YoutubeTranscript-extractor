# YouTube Playlist Transcript Collector

A CLI tool that downloads transcripts for every video in a YouTube playlist and
saves them to a single JSON file.

**No YouTube API key required.**

---

## Requirements

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — playlist metadata extraction
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) — transcript fetching

---

## Setup

```bash
# 1. Clone or download this repository
git clone https://github.com/vazquez620/youtubetranscript-extractor.git
cd youtubetranscript-extractor

# 2. (Optional) Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Usage

```bash
# Auto-generated output filename (based on playlist title)
python yt_transcript_collector.py <PLAYLIST_URL>

# Specify a custom output filename
python yt_transcript_collector.py <PLAYLIST_URL> output.json
```

### Examples

```bash
# Collect transcripts from a public playlist
python yt_transcript_collector.py "https://www.youtube.com/playlist?list=PLxxxxxx"

# Save to a specific file
python yt_transcript_collector.py "https://www.youtube.com/playlist?list=PLxxxxxx" my_transcripts.json
```

### Terminal output

```
Fetching playlist metadata from:
  https://www.youtube.com/playlist?list=PLxxxxxx

Playlist : My Awesome Playlist
Videos   : 12

[1/12] Introduction to Python
         Collected — en (42 segments)
[2/12] Advanced Topics
         Collected — en (auto-generated) (87 segments)
[3/12] Unlisted Video
         Skipped — Video is unavailable
...

Done!
  Collected : 11/12
  Skipped   : 1/12
  Output    : my_awesome_playlist_transcripts.json
```

---

## Output format

```json
{
  "metadata": {
    "playlist_title": "My Awesome Playlist",
    "playlist_id": "PLxxxxxx",
    "playlist_url": "https://www.youtube.com/playlist?list=PLxxxxxx",
    "collected_at": "2024-01-15T10:30:00+00:00",
    "total_videos": 12,
    "transcripts_collected": 11,
    "transcripts_skipped": 1
  },
  "transcripts": [
    {
      "video_id": "dQw4w9WgXcQ",
      "title": "Introduction to Python",
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "language": "en",
      "segment_count": 42,
      "transcript_text": "Full plain text of the transcript joined together...",
      "transcript_segments": [
        { "start": 0.0, "duration": 3.5, "text": "Hello and welcome" },
        { "start": 3.5, "duration": 4.2, "text": "to this tutorial" }
      ]
    }
  ],
  "skipped": [
    {
      "video_id": "xxxxxxxxxx",
      "title": "Unlisted Video",
      "url": "https://www.youtube.com/watch?v=xxxxxxxxxx",
      "reason": "Video is unavailable"
    }
  ]
}
```

---

## Notes

- **No API key needed** — uses `yt-dlp` for playlist metadata and
  `youtube-transcript-api` for transcripts, both of which scrape YouTube
  directly without requiring authentication.
- Transcript language preference: manually-created English → auto-generated
  English → any available language.
- A 0.3 s delay is added between requests to reduce the chance of rate limiting.
- Videos with no available transcript are silently skipped and recorded in the
  `skipped` array.
