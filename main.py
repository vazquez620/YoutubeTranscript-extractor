"""YouTube Playlist Transcript Downloader — FastAPI backend."""

import asyncio
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from functools import partial

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

app = FastAPI(title="YT Transcript Downloader")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CollectRequest(BaseModel):
    playlist_url: str


# ---------------------------------------------------------------------------
# Core helpers  (blocking — called via run_in_executor)
# ---------------------------------------------------------------------------

def _extract_playlist_info(playlist_url: str) -> tuple[str, str, list[dict]]:
    """Return (playlist_title, playlist_id, videos) using yt-dlp."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)

    if info.get("_type") != "playlist":
        raise ValueError("URL does not appear to be a YouTube playlist.")

    playlist_title = info.get("title", "unknown_playlist")
    playlist_id = info.get("id", "")

    videos = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        vid_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
        title = entry.get("title", "Untitled")
        url = entry.get("url") or f"https://www.youtube.com/watch?v={vid_id}"
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={vid_id}"
        videos.append({"video_id": vid_id, "title": title, "url": url})

    return playlist_title, playlist_id, videos


def _fetch_transcript(video_id: str) -> tuple[list[dict] | None, str]:
    """
    Fetch transcript segments.

    Priority: manual EN → auto-generated EN → any language.
    Returns (segments, language) or (None, reason).
    """
    try:
        tlist = YouTubeTranscriptApi.list_transcripts(video_id)
    except TranscriptsDisabled:
        return None, "Transcripts are disabled for this video"
    except VideoUnavailable:
        return None, "Video is unavailable"
    except Exception as exc:
        return None, f"Could not retrieve transcript list: {exc}"

    transcript = None
    language_code = None

    # 1. Manual English
    try:
        transcript = tlist.find_manually_created_transcript(["en"])
        language_code = "en"
    except NoTranscriptFound:
        pass

    # 2. Auto-generated English
    if transcript is None:
        try:
            transcript = tlist.find_generated_transcript(["en"])
            language_code = "en (auto-generated)"
        except NoTranscriptFound:
            pass

    # 3. Any language
    if transcript is None:
        try:
            all_t = list(tlist)
            if all_t:
                transcript = all_t[0]
                lang = transcript.language_code
                language_code = f"{lang} (auto-generated)" if transcript.is_generated else lang
        except Exception:
            pass

    if transcript is None:
        return None, "No transcript available in any language"

    try:
        raw = transcript.fetch()
        segments = [
            {
                "start": round(float(s.get("start", 0)), 3),
                "duration": round(float(s.get("duration", 0)), 3),
                "text": s.get("text", ""),
            }
            for s in raw
        ]
        return segments, language_code
    except Exception as exc:
        return None, f"Failed to fetch transcript data: {exc}"


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")[:max_len]


def _build_zip(playlist_url: str) -> tuple[bytes, str]:
    """
    Full blocking pipeline: fetch playlist → transcripts → build ZIP in memory.
    Returns (zip_bytes, suggested_filename).
    """
    playlist_title, playlist_id, videos = _extract_playlist_info(playlist_url)
    total = len(videos)

    if total == 0:
        raise ValueError("No videos found in the playlist.")

    collected = []
    skipped = []

    for idx, video in enumerate(videos, start=1):
        vid_id = video["video_id"]
        title = video["title"]
        url = video["url"]

        segments, lang_or_reason = _fetch_transcript(vid_id)

        if segments is None:
            skipped.append(
                {"video_id": vid_id, "title": title, "url": url, "reason": lang_or_reason}
            )
        else:
            transcript_text = " ".join(s["text"] for s in segments)
            collected.append(
                {
                    "index": idx,
                    "video_id": vid_id,
                    "title": title,
                    "url": url,
                    "language": lang_or_reason,
                    "transcript_text": transcript_text,
                    "transcript_segments": segments,
                }
            )

        if idx < total:
            time.sleep(0.3)

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in collected:
            slug = _slugify(item["title"])
            filename = f"{item['index']:03d}_{slug}.json"
            payload = {
                "video_id": item["video_id"],
                "title": item["title"],
                "url": item["url"],
                "language": item["language"],
                "transcript_text": item["transcript_text"],
                "transcript_segments": item["transcript_segments"],
            }
            zf.writestr(filename, json.dumps(payload, ensure_ascii=False, indent=2))

        # Summary of skipped videos
        skipped_summary = {
            "playlist_title": playlist_title,
            "playlist_id": playlist_id,
            "playlist_url": playlist_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "total_videos": total,
            "transcripts_collected": len(collected),
            "transcripts_skipped": len(skipped),
            "skipped_videos": skipped,
        }
        zf.writestr(
            "skipped_videos.json",
            json.dumps(skipped_summary, ensure_ascii=False, indent=2),
        )

    zip_bytes = buf.getvalue()
    zip_name = f"{_slugify(playlist_title)}_transcripts.zip"
    return zip_bytes, zip_name


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/collect")
async def collect(req: CollectRequest):
    if not req.playlist_url.strip():
        raise HTTPException(status_code=400, detail="playlist_url is required.")

    loop = asyncio.get_event_loop()
    try:
        zip_bytes, zip_name = await loop.run_in_executor(
            None, partial(_build_zip, req.playlist_url.strip())
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Collection failed: {exc}")

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )
