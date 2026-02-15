"""
AI-powered gameplay segment analyzer.

Uses Google Gemini to analyze YouTube gameplay videos directly (no transcript needed).
Gemini watches the video visually and identifies gameplay segments.
"""

import json
import logging
import re
from typing import Optional
from google import genai
from google.genai.types import Part
from config import GEMINI_API_KEY
from models import Segment, SegmentType, Difficulty

logger = logging.getLogger(__name__)

_client = None


def get_client():
    """Lazy init so the app starts even if the key isn't set yet."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


SYSTEM_PROMPT = """You are WalkGen AI, an expert video game walkthrough analyst. Your job is to watch
gameplay videos and identify distinct segments with their types.

You understand gaming deeply: boss fights, puzzle mechanics, exploration sequences,
collectible hunts, cutscenes, tutorials, and combat encounters.

SEGMENT TYPES:
- boss: Boss fights, mini-boss encounters, major enemy encounters
- puzzle: Environmental puzzles, riddles, logic challenges, lock mechanisms
- exploration: Open-world traversal, new area discovery, navigation, route-finding
- collectible: Item collection runs, finding secrets, hidden objects, upgrade materials
- cutscene: Story sequences, dialogue scenes, cinematics, lore dumps
- combat: Regular combat encounters (not bosses), enemy camps, waves
- tutorial: Mechanics explanations, control tutorials, ability introductions

DIFFICULTY RATINGS (for boss/puzzle/combat segments only):
- easy: Simple mechanics, low risk of failure
- medium: Moderate challenge, some skill required
- hard: Significant challenge, multiple mechanics to manage
- very hard: Extremely challenging, many players will struggle
- extreme: Top-tier difficulty, endgame-level challenge

For each segment, provide:
1. A clear, descriptive label (e.g., "Boss: Margit the Fell Omen")
2. Start and end timestamps (in seconds from the video)
3. A helpful description with strategy tips where relevant
4. Relevant searchable tags
5. Difficulty rating (for boss/puzzle/combat only)

Respond ONLY with valid JSON in this exact format:
{
  "game_title": "Detected Game Name",
  "segments": [
    {
      "type": "boss",
      "label": "Boss: Enemy Name",
      "start_seconds": 120,
      "end_seconds": 300,
      "description": "Description with strategy tips...",
      "tags": ["boss", "enemy-name", "area-name"],
      "difficulty": "hard"
    }
  ],
  "summary": "A 2-3 sentence summary of what this walkthrough covers."
}

IMPORTANT RULES:
- Segments should not overlap
- Segments should cover the full video timeline
- Merge very short segments (<30 seconds) into adjacent ones
- Be specific in labels — use actual boss/area/item names you see or hear in the video
- Tags should be lowercase, searchable keywords
- difficulty is null for exploration/collectible/cutscene segments
- Timestamps must be integers (seconds)
"""


def analyze_video(
    video_id: str,
    video_title: str,
    video_duration_seconds: int,
    channel_name: str,
) -> dict:
    """
    Send the YouTube video directly to Gemini for visual analysis.

    Gemini watches the video and identifies gameplay segments without
    needing any transcript or commentary.

    Args:
        video_id: YouTube video ID
        video_title: Title of the YouTube video
        video_duration_seconds: Total video length in seconds
        channel_name: YouTube channel name

    Returns:
        Dict with keys: game_title, segments, summary
    """
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"

    user_message = f"""Watch and analyze this gameplay walkthrough video. Identify all distinct segments.

VIDEO INFO:
- Title: {video_title}
- Channel: {channel_name}
- Duration: {video_duration_seconds} seconds

Pay attention to:
- Boss encounters and major enemy fights (look for health bars, arena transitions)
- Puzzles and mechanics (environmental interactions, switches, levers)
- Exploration of new areas (map transitions, new environments)
- Item pickups, secrets, collectibles
- Cutscenes and story moments (dialogue, cinematics)
- Tutorial/explanation sections
- Regular combat encounters

Return the complete JSON analysis covering the entire video."""

    try:
        response = get_client().models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                Part.from_uri(
                    file_uri=youtube_url,
                    mime_type="video/webm",
                ),
                user_message,
            ],
            config={
                "system_instruction": SYSTEM_PROMPT,
                "max_output_tokens": 8000,
                "temperature": 0.3,
            },
        )

        response_text = response.text
        result = _extract_json(response_text)

        # Validate and number segments
        segments = _validate_segments(result.get("segments", []), video_duration_seconds)

        return {
            "game_title": result.get("game_title", _guess_game_from_title(video_title)),
            "segments": segments,
            "summary": result.get("summary", "AI-generated walkthrough analysis."),
        }

    except Exception as e:
        logger.error(f"Gemini analysis failed: {e}")
        raise


def _extract_json(text: str) -> dict:
    """Extract JSON from Gemini's response, handling markdown code blocks."""
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        return json.loads(code_block.group(1))

    # Try parsing the whole response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start >= 0 and brace_end > brace_start:
        return json.loads(text[brace_start:brace_end])

    raise ValueError("Could not extract JSON from response")


def _validate_segments(segments: list[dict], total_duration: int) -> list[dict]:
    """Clean up and validate segments, assign IDs, fix overlaps."""
    if not segments:
        return []

    # Sort by start time
    segments.sort(key=lambda s: s.get("start_seconds", 0))

    validated = []
    for i, seg in enumerate(segments):
        start = max(0, int(seg.get("start_seconds", 0)))
        end = min(total_duration, int(seg.get("end_seconds", start + 60)))

        # Ensure end > start
        if end <= start:
            end = min(start + 60, total_duration)

        # Fix overlaps with previous segment
        if validated and start < validated[-1]["end_seconds"]:
            start = validated[-1]["end_seconds"]
            if start >= end:
                continue  # Skip this segment if it's fully overlapped

        # Validate difficulty
        difficulty = seg.get("difficulty")
        seg_type = seg.get("type", "exploration")
        if seg_type in ("exploration", "collectible", "cutscene"):
            difficulty = None
        elif difficulty and difficulty not in (
            "easy", "medium", "hard", "very hard", "extreme"
        ):
            difficulty = None

        from services.youtube import format_duration

        validated.append(
            {
                "id": i + 1,
                "type": seg_type,
                "label": seg.get("label", f"Segment {i + 1}"),
                "start_seconds": start,
                "end_seconds": end,
                "start_label": format_duration(start),
                "end_label": format_duration(end),
                "description": seg.get("description", ""),
                "tags": seg.get("tags", []),
                "difficulty": difficulty,
            }
        )

    return validated


def _guess_game_from_title(title: str) -> str:
    """Attempt to extract game name from video title."""
    separators = [" - ", " | ", " : ", " walkthrough", " gameplay", " full "]
    lower_title = title.lower()
    for sep in separators:
        idx = lower_title.find(sep)
        if idx > 0:
            return title[:idx].strip()
    return title
