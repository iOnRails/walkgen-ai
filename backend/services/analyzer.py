"""
AI-powered gameplay segment analyzer.

Takes a formatted transcript from a gameplay video and uses Claude to identify
and classify segments (boss fights, puzzles, exploration, collectibles, cutscenes).
"""

import json
import logging
from typing import Optional
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, TRANSCRIPT_CHUNK_SIZE
from models import Segment, SegmentType, Difficulty

logger = logging.getLogger(__name__)

_client = None

def get_client():
    """Lazy init so the app starts even if the key isn't set yet."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client

SYSTEM_PROMPT = """You are WalkGen AI, an expert video game walkthrough analyst. Your job is to analyze
gameplay video transcripts and identify distinct segments with their types.

You understand gaming terminology deeply: boss fights, puzzle mechanics, exploration sequences,
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
2. Start and end timestamps (from the transcript timestamps)
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
- Be specific in labels — use actual boss/area/item names from the transcript
- Tags should be lowercase, searchable keywords
- difficulty is null for exploration/collectible/cutscene segments
- Timestamps must be integers (seconds)
"""


def analyze_transcript(
    formatted_transcript: str,
    video_title: str,
    video_duration_seconds: int,
    channel_name: str,
) -> dict:
    """
    Send the transcript to Claude for segment analysis.

    Args:
        formatted_transcript: Timestamped transcript text
        video_title: Title of the YouTube video
        video_duration_seconds: Total video length in seconds
        channel_name: YouTube channel name

    Returns:
        Dict with keys: game_title, segments, summary
    """
    # Build the user message with context
    user_message = f"""Analyze this gameplay walkthrough video and identify all segments.

VIDEO INFO:
- Title: {video_title}
- Channel: {channel_name}
- Duration: {video_duration_seconds} seconds

TRANSCRIPT:
{formatted_transcript}

Identify every distinct segment in this walkthrough. Pay attention to:
- When the narrator mentions boss names or says "boss fight", "boss encounter"
- When puzzles or mechanics are being explained
- When exploring new areas or backtracking
- When collecting items, secrets, or upgrade materials
- When cutscenes or story moments occur
- Tutorial/explanation sections

Return the complete JSON analysis."""

    # If transcript is very long, we may need to chunk it
    if len(formatted_transcript) > TRANSCRIPT_CHUNK_SIZE * 3:
        return _analyze_chunked(
            formatted_transcript, video_title, video_duration_seconds, channel_name
        )

    try:
        response = get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract JSON from response
        response_text = response.content[0].text
        result = _extract_json(response_text)

        # Validate and number segments
        segments = _validate_segments(result.get("segments", []), video_duration_seconds)

        return {
            "game_title": result.get("game_title", _guess_game_from_title(video_title)),
            "segments": segments,
            "summary": result.get("summary", "AI-generated walkthrough analysis."),
        }

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise


def _analyze_chunked(
    transcript: str,
    video_title: str,
    duration: int,
    channel: str,
) -> dict:
    """
    For very long videos, analyze the transcript in chunks and merge results.
    """
    lines = transcript.split("\n")
    chunk_size = len(lines) // 3  # Split into 3 chunks
    chunks = [
        "\n".join(lines[i : i + chunk_size])
        for i in range(0, len(lines), chunk_size)
    ]

    all_segments = []
    game_title = None
    summaries = []

    for i, chunk in enumerate(chunks):
        chunk_label = f"Part {i + 1}/{len(chunks)}"
        user_message = f"""Analyze this SECTION of a gameplay walkthrough ({chunk_label}).

VIDEO: {video_title} by {channel} ({duration}s total)

TRANSCRIPT SECTION:
{chunk}

Return JSON with segments found in this section only."""

        try:
            response = get_client().messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            result = _extract_json(response.content[0].text)
            all_segments.extend(result.get("segments", []))

            if not game_title:
                game_title = result.get("game_title")

            if result.get("summary"):
                summaries.append(result["summary"])

        except Exception as e:
            logger.warning(f"Chunk {i + 1} analysis failed: {e}")
            continue

    segments = _validate_segments(all_segments, duration)

    return {
        "game_title": game_title or _guess_game_from_title(video_title),
        "segments": segments,
        "summary": " ".join(summaries) if summaries else "AI-generated walkthrough.",
    }


def _extract_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    import re

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
    # Common patterns: "Game Name - Walkthrough", "Game Name Full Walkthrough"
    separators = [" - ", " | ", " : ", " walkthrough", " gameplay", " full "]
    lower_title = title.lower()
    for sep in separators:
        idx = lower_title.find(sep)
        if idx > 0:
            return title[:idx].strip()
    return title
