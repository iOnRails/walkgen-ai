"""
SQLite-based caching layer for walkthrough results.

Stores analyzed walkthroughs so repeat requests for the same video
are instant (no API costs, no wait time).

In production, swap this for PostgreSQL or Redis for better concurrency.
"""

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Use /data for persistent storage (Railway Volume), fallback to app dir for local dev
_data_dir = Path("/data")
if _data_dir.exists() and _data_dir.is_dir():
    DB_PATH = _data_dir / "walkgen_cache.db"
else:
    DB_PATH = Path(__file__).parent.parent / "walkgen_cache.db"


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode for better concurrency."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS walkthroughs (
                video_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                video_title TEXT,
                channel TEXT,
                game_title TEXT,
                duration_seconds INTEGER,
                duration_label TEXT,
                thumbnail_url TEXT,
                summary TEXT,
                total_segments INTEGER,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 1,
                last_accessed TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_walkthroughs_game
                ON walkthroughs(game_title);

            CREATE INDEX IF NOT EXISTS idx_walkthroughs_created
                ON walkthroughs(created_at);

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                segment_id INTEGER NOT NULL,
                parent_id INTEGER,
                nickname TEXT NOT NULL DEFAULT 'Anonymous',
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES walkthroughs(video_id)
            );

            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (comment_id) REFERENCES comments(id),
                UNIQUE(comment_id, session_id, emoji)
            );

            CREATE INDEX IF NOT EXISTS idx_comments_video_segment
                ON comments(video_id, segment_id);

            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT,
                FOREIGN KEY (video_id) REFERENCES walkthroughs(video_id)
            );
        """)
        conn.commit()
        logger.info(f"Cache database initialized at {DB_PATH}")
    finally:
        conn.close()


def get_cached_walkthrough(video_id: str) -> Optional[dict]:
    """
    Look up a cached walkthrough by YouTube video ID.

    Returns the full walkthrough dict if found, None if not cached.
    Also bumps the access count and last_accessed timestamp.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data_json FROM walkthroughs WHERE video_id = ?",
            (video_id,),
        ).fetchone()

        if row:
            # Bump access stats
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE walkthroughs SET access_count = access_count + 1, last_accessed = ? WHERE video_id = ?",
                (now, video_id),
            )
            conn.commit()

            # Log the cache hit
            conn.execute(
                "INSERT INTO analytics (video_id, event_type, timestamp) VALUES (?, 'cache_hit', ?)",
                (video_id, now),
            )
            conn.commit()

            logger.info(f"Cache HIT for video {video_id}")
            return json.loads(row["data_json"])

        logger.info(f"Cache MISS for video {video_id}")
        return None
    finally:
        conn.close()


def save_walkthrough(video_id: str, job_id: str, walkthrough: dict):
    """
    Save a completed walkthrough to the cache.

    Args:
        video_id: YouTube video ID
        job_id: Analysis job ID
        walkthrough: Full walkthrough dict (serializable)
    """
    conn = get_connection()
    try:
        video = walkthrough.get("video", {})
        now = datetime.utcnow().isoformat()

        conn.execute(
            """INSERT OR REPLACE INTO walkthroughs
               (video_id, job_id, video_title, channel, game_title,
                duration_seconds, duration_label, thumbnail_url,
                summary, total_segments, data_json, created_at,
                access_count, last_accessed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                video_id,
                job_id,
                video.get("title", ""),
                video.get("channel", ""),
                video.get("game_title", ""),
                video.get("duration_seconds", 0),
                video.get("duration_label", ""),
                video.get("thumbnail_url", ""),
                walkthrough.get("summary", ""),
                walkthrough.get("total_segments", 0),
                json.dumps(walkthrough),
                now,
                now,
            ),
        )

        # Log the save event
        conn.execute(
            "INSERT INTO analytics (video_id, event_type, timestamp) VALUES (?, 'analyzed', ?)",
            (video_id, now),
        )

        conn.commit()
        logger.info(f"Cached walkthrough for video {video_id} ({walkthrough.get('total_segments', 0)} segments)")
    finally:
        conn.close()


def get_recent_walkthroughs(limit: int = 20) -> list[dict]:
    """Get recently analyzed walkthroughs for the browse/discover page."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT video_id, job_id, video_title, channel, game_title,
                      duration_label, thumbnail_url, total_segments, access_count, created_at
               FROM walkthroughs
               ORDER BY last_accessed DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_popular_walkthroughs(limit: int = 10) -> list[dict]:
    """Get most-accessed walkthroughs."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT video_id, job_id, video_title, channel, game_title,
                      duration_label, thumbnail_url, total_segments, access_count
               FROM walkthroughs
               ORDER BY access_count DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def search_walkthroughs(query: str, limit: int = 20) -> list[dict]:
    """Search cached walkthroughs by game title, video title, or channel."""
    conn = get_connection()
    try:
        q = f"%{query}%"
        rows = conn.execute(
            """SELECT video_id, job_id, video_title, channel, game_title,
                      duration_label, thumbnail_url, total_segments, access_count
               FROM walkthroughs
               WHERE video_title LIKE ? OR game_title LIKE ? OR channel LIKE ?
               ORDER BY access_count DESC
               LIMIT ?""",
            (q, q, q, limit),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


# ─── Comments & Reactions ───

def add_comment(video_id: str, segment_id: int, text: str, nickname: str = "Anonymous", parent_id: int = None) -> dict:
    """Add an anonymous comment to a segment."""
    conn = get_connection()
    try:
        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            """INSERT INTO comments (video_id, segment_id, parent_id, nickname, text, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (video_id, segment_id, parent_id, nickname or "Anonymous", text, now),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "video_id": video_id,
            "segment_id": segment_id,
            "parent_id": parent_id,
            "nickname": nickname or "Anonymous",
            "text": text,
            "created_at": now,
            "reactions": {},
            "replies": [],
        }
    finally:
        conn.close()


def get_comments(video_id: str, segment_id: int = None) -> list[dict]:
    """Get comments for a video (optionally filtered by segment). Returns threaded structure."""
    conn = get_connection()
    try:
        if segment_id is not None:
            rows = conn.execute(
                "SELECT * FROM comments WHERE video_id = ? AND segment_id = ? ORDER BY created_at ASC",
                (video_id, segment_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM comments WHERE video_id = ? ORDER BY created_at ASC",
                (video_id,),
            ).fetchall()

        comments = [dict(row) for row in rows]

        # Get reactions for all comments
        comment_ids = [c["id"] for c in comments]
        reactions_map = {}
        if comment_ids:
            placeholders = ",".join("?" * len(comment_ids))
            reaction_rows = conn.execute(
                f"SELECT comment_id, emoji, COUNT(*) as count FROM reactions WHERE comment_id IN ({placeholders}) GROUP BY comment_id, emoji",
                comment_ids,
            ).fetchall()
            for r in reaction_rows:
                cid = r["comment_id"]
                if cid not in reactions_map:
                    reactions_map[cid] = {}
                reactions_map[cid][r["emoji"]] = r["count"]

        # Build threaded structure
        comment_map = {}
        top_level = []
        for c in comments:
            c["reactions"] = reactions_map.get(c["id"], {})
            c["replies"] = []
            comment_map[c["id"]] = c

        for c in comments:
            if c["parent_id"] and c["parent_id"] in comment_map:
                comment_map[c["parent_id"]]["replies"].append(c)
            else:
                top_level.append(c)

        return top_level
    finally:
        conn.close()


def toggle_reaction(comment_id: int, emoji: str, session_id: str) -> dict:
    """Toggle a reaction emoji on a comment. Returns updated reaction counts."""
    conn = get_connection()
    try:
        now = datetime.utcnow().isoformat()
        existing = conn.execute(
            "SELECT id FROM reactions WHERE comment_id = ? AND session_id = ? AND emoji = ?",
            (comment_id, session_id, emoji),
        ).fetchone()

        if existing:
            conn.execute("DELETE FROM reactions WHERE id = ?", (existing["id"],))
        else:
            conn.execute(
                "INSERT INTO reactions (comment_id, emoji, session_id, created_at) VALUES (?, ?, ?, ?)",
                (comment_id, emoji, session_id, now),
            )
        conn.commit()

        # Return updated counts
        rows = conn.execute(
            "SELECT emoji, COUNT(*) as count FROM reactions WHERE comment_id = ? GROUP BY emoji",
            (comment_id,),
        ).fetchall()

        return {r["emoji"]: r["count"] for r in rows}
    finally:
        conn.close()


def get_cache_stats() -> dict:
    """Get cache statistics for the admin/health endpoint."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) as n FROM walkthroughs").fetchone()["n"]
        total_hits = conn.execute("SELECT SUM(access_count) as n FROM walkthroughs").fetchone()["n"] or 0
        popular = conn.execute(
            "SELECT game_title, COUNT(*) as n FROM walkthroughs GROUP BY game_title ORDER BY n DESC LIMIT 5"
        ).fetchall()

        return {
            "total_cached": total,
            "total_cache_hits": total_hits,
            "top_games": [{"game": r["game_title"], "count": r["n"]} for r in popular],
        }
    finally:
        conn.close()
