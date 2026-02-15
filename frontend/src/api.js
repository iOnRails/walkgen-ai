/**
 * WalkGen AI - API Client
 *
 * Communicates with the FastAPI backend for video analysis.
 */

// In production, use relative URL so Vercel rewrites work (see vercel.json)
// In development, point to local backend
const API_BASE = process.env.REACT_APP_API_URL || "";

export async function startAnalysis(url) {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Analysis failed (${res.status})`);
  }

  return res.json();
}

export async function getJobStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed (${res.status})`);
  return res.json();
}

export async function getWalkthrough(jobId) {
  const res = await fetch(`${API_BASE}/api/walkthrough/${jobId}`);
  if (!res.ok) throw new Error(`Failed to get walkthrough (${res.status})`);
  return res.json();
}

export async function searchYouTube(query) {
  const res = await fetch(`${API_BASE}/api/youtube/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Search failed (${res.status})`);
  }
  return res.json();
}

// ─── Browse / Discover ───

export async function getRecentWalkthroughs(limit = 20) {
  const res = await fetch(`${API_BASE}/api/browse/recent?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to load recent walkthroughs");
  return res.json();
}

export async function getPopularWalkthroughs(limit = 10) {
  const res = await fetch(`${API_BASE}/api/browse/popular?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to load popular walkthroughs");
  return res.json();
}

export async function searchBrowse(query) {
  const res = await fetch(`${API_BASE}/api/browse/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}

// ─── Comments & Reactions ───

export async function getComments(videoId, segmentId) {
  const params = segmentId != null ? `?segment_id=${segmentId}` : "";
  const res = await fetch(`${API_BASE}/api/comments/${videoId}${params}`);
  if (!res.ok) throw new Error("Failed to load comments");
  return res.json();
}

export async function postComment(videoId, segmentId, text, nickname, parentId) {
  const res = await fetch(`${API_BASE}/api/comments/${videoId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      segment_id: segmentId,
      text,
      nickname: nickname || "Anonymous",
      parent_id: parentId || null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to post comment");
  }
  return res.json();
}

export async function toggleReaction(commentId, emoji, sessionId) {
  const res = await fetch(`${API_BASE}/api/reactions/${commentId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ emoji, session_id: sessionId }),
  });
  if (!res.ok) throw new Error("Failed to toggle reaction");
  return res.json();
}

/**
 * Poll for job completion.
 * Calls onProgress with each status update.
 * Returns the final walkthrough when complete.
 */
export async function pollUntilComplete(jobId, onProgress, intervalMs = 1500) {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const status = await getJobStatus(jobId);
        onProgress(status);

        if (status.status === "complete") {
          resolve(status.walkthrough);
        } else if (status.status === "error") {
          reject(new Error(status.error || "Analysis failed"));
        } else {
          setTimeout(poll, intervalMs);
        }
      } catch (err) {
        reject(err);
      }
    };

    poll();
  });
}
