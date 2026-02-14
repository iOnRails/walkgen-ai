from pydantic import BaseModel
from typing import Optional
from enum import Enum


class SegmentType(str, Enum):
    boss = "boss"
    puzzle = "puzzle"
    exploration = "exploration"
    collectible = "collectible"
    cutscene = "cutscene"
    combat = "combat"
    tutorial = "tutorial"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"
    very_hard = "very hard"
    extreme = "extreme"


class Segment(BaseModel):
    id: int
    type: SegmentType
    label: str
    start_seconds: int
    end_seconds: int
    start_label: str
    end_label: str
    description: str
    tags: list[str] = []
    difficulty: Optional[Difficulty] = None


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    channel: str
    duration_seconds: int
    duration_label: str
    platform: str = "youtube"
    thumbnail_url: Optional[str] = None
    game_title: Optional[str] = None


class Walkthrough(BaseModel):
    id: str
    video: VideoMetadata
    segments: list[Segment]
    summary: str
    total_segments: int


class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str  # "queued" | "fetching" | "analyzing" | "complete" | "error"
    message: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int  # 0-100
    message: str
    walkthrough: Optional[Walkthrough] = None
    error: Optional[str] = None
