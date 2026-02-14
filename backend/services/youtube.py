"""
YouTube video metadata and transcript extraction service.

Uses:
- youtube-transcript-api (no API key needed) for captions/transcripts
- YouTube Data API v3 (API key required) for metadata (title, duration, channel)
"""

import re
import logging
from typing import Optional
from config import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # raw video ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def format_duration(seconds: int) -> str:
    """Convert seconds to H:MM:SS or M:SS format."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_iso_duration(iso_duration: str) -> int:
    """Parse ISO 8601 duration (PT1H2M3S) to seconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def get_video_metadata(video_id: str) -> dict:
    """
    Fetch video metadata from YouTube Data API.

    Returns dict with: title, channel, duration_seconds, duration_label, thumbnail_url
    """
    try:
        from googleapiclient.discovery import build
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        response = (
            youtube.videos()
            .list(part="snippet,contentDetails,statistics", id=video_id)
            .execute()
        )

        if not response.get("items"):
            raise ValueError(f"Video not found: {video_id}")

        item = response["items"][0]
        snippet = item["snippet"]
        content = item["contentDetails"]

        duration_sec = parse_iso_duration(content["duration"])

        return {
            "video_id": video_id,
            "title": snippet["title"],
            "channel": snippet["channelTitle"],
            "duration_seconds": duration_sec,
            "duration_label": format_duration(duration_sec),
            "thumbnail_url": snippet["thumbnails"].get("high", {}).get("url"),
            "platform": "youtube",
        }
    except Exception as e:
        logger.error(f"Failed to fetch metadata for {video_id}: {e}")
        raise


def get_transcript(video_id: str) -> list[dict]:
    """
    Fetch the transcript/captions for a YouTube video.

    Returns list of dicts: [{"text": "...", "start": 0.0, "duration": 3.5}, ...]

    Compatible with youtube-transcript-api v0.6.x
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Try fetching directly — simplest approach, works on most versions
        try:
            raw = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            # Normalize: ensure each entry has text, start, duration
            return [
                {
                    "text": str(entry.get("text", entry.get("value", ""))),
                    "start": float(entry.get("start", entry.get("offset", 0))),
                    "duration": float(entry.get("duration", 3)),
                }
                for entry in raw
            ]
        except Exception as e1:
            logger.warning(f"Direct transcript fetch failed: {e1}, trying fallback...")

        # Fallback: list transcripts and pick one
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(["en"])
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(["en"])
            except Exception:
                for t in transcript_list:
                    transcript = t.translate("en")
                    break

        if transcript is None:
            raise ValueError(f"No transcript available for video {video_id}")

        raw = transcript.fetch()

        # Normalize output format
        result = []
        for entry in raw:
            if isinstance(entry, dict):
                result.append({
                    "text": str(entry.get("text", "")),
                    "start": float(entry.get("start", 0)),
                    "duration": float(entry.get("duration", 3)),
                })
            else:
                # Some versions return objects with attributes
                result.append({
                    "text": str(getattr(entry, "text", getattr(entry, "value", ""))),
                    "start": float(getattr(entry, "start", getattr(entry, "offset", 0))),
                    "duration": float(getattr(entry, "duration", 3)),
                })

        return result

    except Exception as e:
        logger.error(f"Failed to fetch transcript for {video_id}: {e}")
        raise


def format_transcript_for_analysis(transcript: list[dict]) -> str:
    """
    Convert raw transcript entries into a formatted string for LLM analysis.

    Groups text into ~30-second chunks with timestamps for easier analysis.
    """
    if not transcript:
        return ""

    chunks = []
    current_chunk_text = []
    current_chunk_start = transcript[0]["start"]
    chunk_duration = 0

    for entry in transcript:
        current_chunk_text.append(entry["text"])
        chunk_duration += entry.get("duration", 3)

        # Group into ~30-second chunks
        if chunk_duration >= 30:
            timestamp = format_duration(int(current_chunk_start))
            text = " ".join(current_chunk_text)
            chunks.append(f"[{timestamp}] {text}")
            current_chunk_text = []
            current_chunk_start = entry["start"] + entry.get("duration", 3)
            chunk_duration = 0

    # Don't forget the last chunk
    if current_chunk_text:
        timestamp = format_duration(int(current_chunk_start))
        text = " ".join(current_chunk_text)
        chunks.append(f"[{timestamp}] {text}")

    return "\n".join(chunks)
