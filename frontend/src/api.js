/**
 * WalkGen AI - API Client
 *
 * Communicates with the FastAPI backend for video analysis.
 */

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

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

  if (!res.ok) {
    throw new Error(`Status check failed (${res.status})`);
  }

  return res.json();
}

export async function getWalkthrough(jobId) {
  const res = await fetch(`${API_BASE}/api/walkthrough/${jobId}`);

  if (!res.ok) {
    throw new Error(`Failed to get walkthrough (${res.status})`);
  }

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
