"""
YouTube video metadata and search service.

Uses YouTube Data API v3 (API key required) for metadata and search.
Video analysis is handled directly by Gemini (no transcript needed).
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


def search_videos(query: str, max_results: int = 8) -> list[dict]:
    """
    Search YouTube for gameplay/walkthrough videos matching a query.

    Automatically appends 'walkthrough gameplay' to the query
    to find relevant gaming videos.

    Returns list of dicts with: video_id, title, channel, thumbnail_url, duration_label
    """
    try:
        from googleapiclient.discovery import build
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        # Enhance query to target walkthrough videos
        search_query = f"{query} walkthrough gameplay"

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
