#!/usr/bin/env python3
"""YouTube Playlist Transcript Collector

Fetches transcripts for all videos in a YouTube playlist and saves them to JSON.
No YouTube API key required.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("Error: yt-dlp not installed. Run: pip install yt-dlp")
    sys.exit(1)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:
    print("Error: youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
    sys.exit(1)


def extract_playlist_info(playlist_url: str) -> tuple[str, list[dict]]:
    """Extract playlist title and video list using yt-dlp (no download)."""
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
    for entry in info.get("entries", []):
        if not entry:
            continue
        vid_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
        title = entry.get("title", "Untitled")
        url = entry.get("url") or f"https://www.youtube.com/watch?v={vid_id}"
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={vid_id}"
        videos.append({"video_id": vid_id, "title": title, "url": url})

    return playlist_title, playlist_id, videos


def fetch_transcript(video_id: str) -> tuple[list[dict], str] | tuple[None, str]:
    """
    Fetch transcript for a video.

    Preference order:
      1. Manually created English (en)
      2. Auto-generated English (en)
      3. Any available language

    Returns (segments, language_code) or (None, reason_string).
    """
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)
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
        transcript = transcript_list.find_manually_created_transcript(["en"])
        language_code = "en"
    except NoTranscriptFound:
        pass

    # 2. Auto-generated English
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(["en"])
            language_code = "en (auto-generated)"
        except NoTranscriptFound:
            pass

    # 3. Any available language
    if transcript is None:
        try:
            all_transcripts = list(transcript_list)
            if all_transcripts:
                transcript = all_transcripts[0]
                lang = transcript.language_code
                is_generated = transcript.is_generated
                language_code = f"{lang} (auto-generated)" if is_generated else lang
        except Exception:
            pass

    if transcript is None:
        return None, "No transcript available in any language"

    try:
        segments = transcript.fetch()
        # Normalise to plain dicts
        normalised = [
            {
                "start": round(float(s.get("start", 0)), 3),
                "duration": round(float(s.get("duration", 0)), 3),
                "text": s.get("text", ""),
            }
            for s in segments
        ]
        return normalised, language_code
    except Exception as exc:
        return None, f"Failed to fetch transcript data: {exc}"


def slugify(text: str) -> str:
    """Convert a string to a safe filename slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")[:80]


def collect(playlist_url: str, output_path: str | None = None) -> None:
    print(f"Fetching playlist metadata from:\n  {playlist_url}\n")

    try:
        playlist_title, playlist_id, videos = extract_playlist_info(playlist_url)
    except Exception as exc:
        print(f"Error fetching playlist: {exc}")
        sys.exit(1)

    total = len(videos)
    print(f"Playlist : {playlist_title}")
    print(f"Videos   : {total}\n")

    if total == 0:
        print("No videos found in playlist. Exiting.")
        sys.exit(0)

    if output_path is None:
        slug = slugify(playlist_title)
        output_path = f"{slug}_transcripts.json"

    transcripts = []
    skipped = []

    for idx, video in enumerate(videos, start=1):
        vid_id = video["video_id"]
        title = video["title"]
        url = video["url"]
        prefix = f"[{idx}/{total}]"

        print(f"{prefix} {title}")

        segments, language_or_reason = fetch_transcript(vid_id)

        if segments is None:
            reason = language_or_reason
            print(f"         Skipped — {reason}")
            skipped.append({"video_id": vid_id, "title": title, "url": url, "reason": reason})
        else:
            transcript_text = " ".join(s["text"] for s in segments)
            transcripts.append(
                {
                    "video_id": vid_id,
                    "title": title,
                    "url": url,
                    "language": language_or_reason,
                    "segment_count": len(segments),
                    "transcript_text": transcript_text,
                    "transcript_segments": segments,
                }
            )
            print(f"         Collected — {language_or_reason} ({len(segments)} segments)")

        if idx < total:
            time.sleep(0.3)

    output = {
        "metadata": {
            "playlist_title": playlist_title,
            "playlist_id": playlist_id,
            "playlist_url": playlist_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "total_videos": total,
            "transcripts_collected": len(transcripts),
            "transcripts_skipped": len(skipped),
        },
        "transcripts": transcripts,
        "skipped": skipped,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone!")
    print(f"  Collected : {len(transcripts)}/{total}")
    print(f"  Skipped   : {len(skipped)}/{total}")
    print(f"  Output    : {output_path}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python yt_transcript_collector.py <PLAYLIST_URL> [output.json]")
        sys.exit(1)

    playlist_url = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) >= 3 else None
    collect(playlist_url, output_path)


if __name__ == "__main__":
    main()
