"""
YouTube video metadata and transcript extraction service.

Uses:
- Supadata.ai API (free, 200 req/month) — primary transcript source (works from cloud)
- youtube-transcript-api v1.2+ (no API key needed) — fallback
- YouTube Data API v3 (API key required) for metadata (title, duration, channel)
"""

import re
import json
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
from config import YOUTUBE_API_KEY, PROXY_USERNAME, PROXY_PASSWORD, SUPADATA_API_KEY

logger = logging.getLogger(__name__)


def _get_ytt_api():
    """Create a YouTubeTranscriptApi instance, with proxy if configured."""
    from youtube_transcript_api import YouTubeTranscriptApi

    if PROXY_USERNAME and PROXY_PASSWORD:
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            logger.info("Using Webshare proxy for YouTube transcript fetching")
            return YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=PROXY_USERNAME,
                    proxy_password=PROXY_PASSWORD,
                )
            )
        except ImportError:
            logger.warning("WebshareProxyConfig not available, using generic proxy")
            # Fallback: use generic HTTP proxy via environment
            pass

    return YouTubeTranscriptApi()


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


def _get_transcript_supadata(video_id: str) -> list[dict]:
    """
    Fetch transcript using Supadata.ai API (works from cloud servers).
    Free tier: 200 requests/month, no credit card needed.
    """
    if not SUPADATA_API_KEY:
        raise ValueError("SUPADATA_API_KEY not configured")

    url = f"https://api.supadata.ai/v1/youtube/transcript?videoId={video_id}&text=false"
    req = Request(url, headers={
        "x-api-key": SUPADATA_API_KEY,
        "Accept": "application/json",
    })

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except URLError as e:
        raise ValueError(f"Supadata API request failed: {e}")

    # Supadata returns: {"content": [{"text": "...", "startSeconds": 0, "endSeconds": 3}, ...]}
    content = data.get("content", [])
    if not content:
        raise ValueError("Supadata returned empty transcript")

    result = []
    for entry in content:
        start = float(entry.get("startSeconds", entry.get("start", 0)))
        end = float(entry.get("endSeconds", entry.get("end", start + 3)))
        result.append({
            "text": entry.get("text", ""),
            "start": start,
            "duration": end - start,
        })

    logger.info(f"Supadata: got {len(result)} transcript entries for {video_id}")
    return result


def _get_transcript_ytt(video_id: str) -> list[dict]:
    """Fetch transcript using youtube-transcript-api (may be blocked on cloud servers)."""
    ytt = _get_ytt_api()

    # Try English first
    try:
        fetched = ytt.fetch(video_id, languages=["en"])
        return fetched.to_raw_data()
    except Exception as e1:
        logger.warning(f"English transcript not found: {e1}")

    # Try listing all available transcripts
    try:
        transcript_list = ytt.list(video_id)
        for transcript in transcript_list:
            try:
                fetched = transcript.translate("en").fetch()
                return fetched.to_raw_data()
            except Exception:
                fetched = transcript.fetch()
                return fetched.to_raw_data()
    except Exception as e2:
        logger.warning(f"Listing transcripts failed: {e2}")

    # Last resort: fetch without language preference
    fetched = ytt.fetch(video_id)
    return fetched.to_raw_data()


def get_transcript(video_id: str) -> list[dict]:
    """
    Fetch the transcript/captions for a YouTube video.

    Returns list of dicts: [{"text": "...", "start": 0.0, "duration": 3.5}, ...]

    Tries multiple sources in order:
    1. Supadata.ai API (works from cloud, free 200 req/month)
    2. youtube-transcript-api with proxy (if configured)
    3. youtube-transcript-api direct (works from home IPs)
    """
    errors = []

    # Method 1: Supadata.ai (most reliable from cloud)
    if SUPADATA_API_KEY:
        try:
            return _get_transcript_supadata(video_id)
        except Exception as e:
            logger.warning(f"Supadata failed: {e}")
            errors.append(f"Supadata: {e}")

    # Method 2: youtube-transcript-api (with proxy if configured)
    try:
        return _get_transcript_ytt(video_id)
    except Exception as e:
        logger.warning(f"youtube-transcript-api failed: {e}")
        errors.append(f"YTT: {e}")

    # All methods failed
    error_msg = " | ".join(errors)
    raise ValueError(
        f"Could not fetch transcript for video {video_id}. "
        f"YouTube blocks cloud server IPs. "
        f"Set up SUPADATA_API_KEY (free at supadata.ai) to fix this. "
        f"Details: {error_msg}"
    )


def search_videos(query: str, max_results: int = 8) -> list[dict]:
    """
    Search YouTube for gameplay/walkthrough videos matching a query.

    Automatically appends 'walkthrough gameplay commentary' to the query
    to find relevant gaming videos with spoken commentary (needed for transcripts).

    Returns list of dicts with: video_id, title, channel, thumbnail_url, duration_label
    """
    try:
        from googleapiclient.discovery import build
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        # Enhance query to target walkthrough/commentary videos
        search_query = f"{query} walkthrough gameplay commentary"

        # Step 1: Search for videos
        search_response = (
            youtube.search()
            .list(
                q=search_query,
                part="snippet",
                type="video",
                maxResults=max_results,
                order="relevance",
                videoCategoryId="20",  # Gaming category
            )
            .execute()
        )

        if not search_response.get("items"):
            return []

        # Step 2: Get durations for all results (requires separate API call)
        video_ids = [item["id"]["videoId"] for item in search_response["items"]]
        details_response = (
            youtube.videos()
            .list(part="contentDetails,statistics", id=",".join(video_ids))
            .execute()
        )

        # Build duration map
        duration_map = {}
        views_map = {}
        for item in details_response.get("items", []):
            vid = item["id"]
            dur_sec = parse_iso_duration(item["contentDetails"]["duration"])
            duration_map[vid] = {
                "seconds": dur_sec,
                "label": format_duration(dur_sec),
            }
            views_map[vid] = int(item.get("statistics", {}).get("viewCount", 0))

        # Step 3: Build results
        results = []
        for item in search_response["items"]:
            vid = item["id"]["videoId"]
            snippet = item["snippet"]
            dur = duration_map.get(vid, {"seconds": 0, "label": "?"})

            # Skip very short videos (< 2 min) — unlikely to be walkthroughs
            if dur["seconds"] < 120:
                continue

            results.append({
                "video_id": vid,
                "title": snippet["title"],
                "channel": snippet["channelTitle"],
                "thumbnail_url": snippet["thumbnails"].get("high", snippet["thumbnails"].get("default", {})).get("url", ""),
                "duration_seconds": dur["seconds"],
                "duration_label": dur["label"],
                "views": views_map.get(vid, 0),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })

        return results

    except Exception as e:
        logger.error(f"YouTube search failed: {e}")
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
    current_chunk_start = transcript[0].get("start", 0)
    chunk_duration = 0

    for entry in transcript:
        current_chunk_text.append(entry.get("text", ""))
        chunk_duration += entry.get("duration", 3)

        # Group into ~30-second chunks
        if chunk_duration >= 30:
            timestamp = format_duration(int(current_chunk_start))
            text = " ".join(current_chunk_text)
            chunks.append(f"[{timestamp}] {text}")
            current_chunk_text = []
            current_chunk_start = entry.get("start", 0) + entry.get("duration", 3)
            chunk_duration = 0

    # Don't forget the last chunk
    if current_chunk_text:
        timestamp = format_duration(int(current_chunk_start))
        text = " ".join(current_chunk_text)
        chunks.append(f"[{timestamp}] {text}")

    return "\n".join(chunks)
