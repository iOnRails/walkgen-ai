"""
WalkGen AI - FastAPI Backend

Endpoints:
  POST /api/analyze          - Start analyzing a YouTube video
  GET  /api/status/{id}      - Check job progress
  GET  /api/walkthrough/{id} - Get completed walkthrough
  GET  /api/browse/recent    - Recently analyzed walkthroughs
  GET  /api/browse/popular   - Most-viewed walkthroughs
  GET  /api/browse/search    - Search cached walkthroughs
  GET  /api/health           - Health check + cache stats
"""

import uuid
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from models import (
    AnalyzeRequest,
    AnalyzeResponse,
    JobStatus,
    Walkthrough,
    VideoMetadata,
)
from services.youtube import (
    extract_video_id,
    get_video_metadata,
    search_videos,
)
from services.analyzer import analyze_video
from services.cache import (
    init_db,
    get_cached_walkthrough,
    save_walkthrough,
    get_recent_walkthroughs,
    get_popular_walkthroughs,
    search_walkthroughs,
    get_cache_stats,
    add_comment,
    get_comments,
    toggle_reaction,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="WalkGen AI",
    description="AI-powered video game walkthrough generator",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize cache database on startup
@app.on_event("startup")
async def startup():
    init_db()
    logger.info("WalkGen AI started with SQLite cache")

# In-memory job store for active jobs (cache handles persistence)
jobs: dict[str, dict] = {}


# ─── Health & Stats ───

@app.get("/api/health")
async def health():
    stats = get_cache_stats()
    return {
        "status": "ok",
        "version": "0.3.0",
        "timestamp": datetime.utcnow().isoformat(),
        "cache": stats,
    }


# ─── Browse / Discover ───

@app.get("/api/browse/recent")
async def browse_recent(limit: int = Query(default=20, le=50)):
    """Get recently analyzed walkthroughs (for the discover page)."""
    return {"walkthroughs": get_recent_walkthroughs(limit)}


@app.get("/api/browse/popular")
async def browse_popular(limit: int = Query(default=10, le=50)):
    """Get most-accessed walkthroughs."""
    return {"walkthroughs": get_popular_walkthroughs(limit)}


@app.get("/api/browse/search")
async def browse_search(q: str = Query(..., min_length=1), limit: int = Query(default=20, le=50)):
    """Search cached walkthroughs by game, video title, or channel."""
    return {"query": q, "walkthroughs": search_walkthroughs(q, limit)}


# ─── YouTube Search (AI Find) ───

@app.get("/api/youtube/search")
async def youtube_search(q: str = Query(..., min_length=2), limit: int = Query(default=8, le=20)):
    """
    Search YouTube for gameplay walkthrough videos.

    The query is automatically enhanced with 'walkthrough gameplay commentary'
    to find relevant gaming videos for analysis.
    Filters out short videos (<2 min) that are unlikely to be walkthroughs.
    """
    try:
        results = search_videos(q, max_results=limit)
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube search failed: {str(e)}")


# ─── Comments & Reactions ───

@app.get("/api/comments/{video_id}")
async def list_comments(video_id: str, segment_id: int = Query(default=None)):
    """Get comments for a video, optionally filtered by segment."""
    return {"comments": get_comments(video_id, segment_id)}


@app.post("/api/comments/{video_id}")
async def create_comment(video_id: str, body: dict):
    """Add an anonymous comment to a segment."""
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment text is required")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Comment too long (max 1000 chars)")

    segment_id = body.get("segment_id")
    if segment_id is None:
        raise HTTPException(status_code=400, detail="segment_id is required")

    nickname = body.get("nickname", "Anonymous").strip()[:30] or "Anonymous"
    parent_id = body.get("parent_id")

    comment = add_comment(video_id, segment_id, text, nickname, parent_id)
    return comment


@app.post("/api/reactions/{comment_id}")
async def react_to_comment(comment_id: int, body: dict):
    """Toggle a reaction emoji on a comment."""
    emoji = body.get("emoji", "").strip()
    session_id = body.get("session_id", "").strip()

    allowed_emojis = ["thumbsup", "fire", "laugh", "heart", "skull", "mind_blown"]
    if emoji not in allowed_emojis:
        raise HTTPException(status_code=400, detail=f"Emoji must be one of: {allowed_emojis}")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    reactions = toggle_reaction(comment_id, emoji, session_id)
    return {"reactions": reactions}


# ─── Analysis ───

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_video(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Start analyzing a YouTube gameplay video.

    First checks the cache — if this video was already analyzed, returns
    the cached result instantly (no API costs).
    """
    # Extract video ID
    video_id = extract_video_id(request.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    # ── Check cache first (instant, free) ──
    cached = get_cached_walkthrough(video_id)
    if cached:
        # Put it in the jobs store so status/walkthrough endpoints work
        cache_job_id = cached.get("id", video_id[:8])
        jobs[cache_job_id] = {
            "status": "complete",
            "progress": 100,
            "message": "Loaded from cache (instant!)",
            "video_id": video_id,
            "walkthrough": cached,
            "error": None,
        }
        return AnalyzeResponse(
            job_id=cache_job_id,
            status="complete",
            message="This video was already analyzed. Loading from cache.",
        )

    # ── Check in-memory jobs ──
    for job_id, job in jobs.items():
        if job.get("video_id") == video_id:
            if job["status"] == "complete":
                return AnalyzeResponse(
                    job_id=job_id,
                    status="complete",
                    message="Already analyzed.",
                )
            elif job["status"] not in ("error",):
                return AnalyzeResponse(
                    job_id=job_id,
                    status=job["status"],
                    message="Analysis already in progress.",
                )

    # ── Start new analysis ──
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Queued for analysis...",
        "video_id": video_id,
        "walkthrough": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    background_tasks.add_task(run_analysis, job_id, video_id)

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        message="Analysis started. Poll /api/status/{job_id} for progress.",
    )


@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Check the status of an analysis job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    walkthrough = None
    if job["status"] == "complete" and job["walkthrough"]:
        walkthrough = job["walkthrough"]

    return JobStatus(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        message=job["message"],
        walkthrough=walkthrough,
        error=job.get("error"),
    )


@app.get("/api/walkthrough/{job_id}")
async def get_walkthrough(job_id: str):
    """Get the completed walkthrough for an analysis job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(status_code=202, detail=f"Still in progress: {job['status']}")

    if not job["walkthrough"]:
        raise HTTPException(status_code=500, detail="Walkthrough data missing")

    return job["walkthrough"]


# ─── Background Analysis Pipeline ───

async def run_analysis(job_id: str, video_id: str):
    """
    Full analysis pipeline:
    1. Fetch video metadata from YouTube
    2. Send video to Gemini for direct visual analysis
    3. Save to cache for future instant access
    """
    try:
        # Step 1: Fetch metadata
        jobs[job_id]["status"] = "fetching"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = "Fetching video metadata from YouTube..."

        metadata = await asyncio.to_thread(get_video_metadata, video_id)

        jobs[job_id]["progress"] = 20
        jobs[job_id]["message"] = f"Found: {metadata['title']}"

        # Step 2: AI analysis (Gemini watches the video directly)
        jobs[job_id]["status"] = "analyzing"
        jobs[job_id]["progress"] = 30
        jobs[job_id]["message"] = "Gemini is watching and analyzing the video..."

        result = await asyncio.to_thread(
            lambda: analyze_video(
                video_id=video_id,
                video_title=metadata["title"],
                video_duration_seconds=metadata["duration_seconds"],
                channel_name=metadata["channel"],
            )
        )

        jobs[job_id]["progress"] = 90
        jobs[job_id]["message"] = f"Found {len(result['segments'])} segments. Saving..."

        # Step 4: Build walkthrough
        video_meta = VideoMetadata(
            video_id=video_id,
            title=metadata["title"],
            channel=metadata["channel"],
            duration_seconds=metadata["duration_seconds"],
            duration_label=metadata["duration_label"],
            platform="youtube",
            thumbnail_url=metadata.get("thumbnail_url"),
            game_title=result.get("game_title"),
        )

        walkthrough = Walkthrough(
            id=job_id,
            video=video_meta,
            segments=result["segments"],
            summary=result["summary"],
            total_segments=len(result["segments"]),
        )

        # Step 5: Save to cache
        walkthrough_dict = walkthrough.model_dump()
        save_walkthrough(video_id, job_id, walkthrough_dict)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "Analysis complete! Result cached for instant future access."
        jobs[job_id]["walkthrough"] = walkthrough_dict

        logger.info(f"Job {job_id} complete + cached: {len(result['segments'])} segments")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["progress"] = 0
        jobs[job_id]["message"] = "Analysis failed."
        jobs[job_id]["error"] = str(e)
