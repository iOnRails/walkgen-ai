import React, { useState, useCallback } from "react";
import { startAnalysis, pollUntilComplete } from "./api";

/*──────────────────────────── Constants ────────────────────────────*/

const TYPES = {
  boss:        { bg:"#fee2e2", border:"#ef4444", text:"#991b1b", tag:"[B]", label:"Boss Fight" },
  puzzle:      { bg:"#f3e8ff", border:"#a855f7", text:"#6b21a8", tag:"[P]", label:"Puzzle" },
  exploration: { bg:"#dbeafe", border:"#3b82f6", text:"#1e3a5f", tag:"[E]", label:"Exploration" },
  collectible: { bg:"#fef9c3", border:"#eab308", text:"#713f12", tag:"[C]", label:"Collectible" },
  cutscene:    { bg:"#ccfbf1", border:"#14b8a6", text:"#134e4a", tag:"[S]", label:"Cutscene" },
  combat:      { bg:"#ffe4e6", border:"#f43f5e", text:"#9f1239", tag:"[F]", label:"Combat" },
  tutorial:    { bg:"#e0e7ff", border:"#6366f1", text:"#3730a3", tag:"[T]", label:"Tutorial" },
};

const DIFFS = { easy:"#22c55e", medium:"#eab308", hard:"#f97316", "very hard":"#ef4444", extreme:"#dc2626" };

function fmt(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h > 0 ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}` : `${m}:${String(s).padStart(2,"0")}`;
}

/*──────────────────────────── Small Components ────────────────────────────*/

function Badge({ type }) {
  const c = TYPES[type] || TYPES.exploration;
  return (
    <span style={{ display:"inline-block", padding:"2px 8px", borderRadius:999, fontSize:11, fontWeight:700, background:c.bg, border:`1px solid ${c.border}`, color:c.text }}>
      {c.tag} {c.label}
    </span>
  );
}

function DiffBadge({ difficulty }) {
  if (!difficulty) return null;
  return (
    <span style={{ padding:"2px 7px", borderRadius:999, fontSize:10, fontWeight:700, background:DIFFS[difficulty] || "#94a3b8", color:"#fff", marginLeft:4 }}>
      {difficulty.toUpperCase()}
    </span>
  );
}

function Progress({ pct }) {
  return (
    <div style={{ width:"100%", background:"#e2e8f0", borderRadius:8, overflow:"hidden", height:8 }}>
      <div style={{ width:`${pct}%`, height:"100%", background:"linear-gradient(90deg,#6366f1,#a855f7,#ec4899)", borderRadius:8, transition:"width 0.3s" }} />
    </div>
  );
}

function Header({ onBack }) {
  return (
    <div style={{ borderBottom:"1px solid #e2e8f0", padding:"12px 20px", display:"flex", alignItems:"center", justifyContent:"space-between", background:"#fff" }}>
      <div style={{ cursor:"pointer", display:"flex", alignItems:"center", gap:8 }} onClick={onBack}>
        <div style={{ fontWeight:800, fontSize:18, color:"#6366f1" }}>WalkGen AI</div>
        <div style={{ fontSize:11, color:"#94a3b8" }}>AI-Powered Walkthrough Generator</div>
      </div>
      <span style={{ padding:"3px 10px", borderRadius:999, background:"#f0fdf4", border:"1px solid #bbf7d0", color:"#16a34a", fontSize:10, fontWeight:600 }}>
        Live
      </span>
    </div>
  );
}

function Timeline({ segments, durSec, currentTime, onSeek }) {
  return (
    <div
      onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); onSeek(Math.floor(((e.clientX - r.left) / r.width) * durSec)); }}
      style={{ position:"relative", height:28, background:"#e2e8f0", borderRadius:6, cursor:"pointer", marginTop:8 }}
    >
      {segments.map((seg) => {
        const c = TYPES[seg.type] || TYPES.exploration;
        return (
          <div key={seg.id} title={seg.label} style={{
            position:"absolute",
            left:`${(seg.start_seconds / durSec) * 100}%`,
            width:`${Math.max(((seg.end_seconds - seg.start_seconds) / durSec) * 100, 0.5)}%`,
            height:6, top:11, background:c.border,
            opacity: currentTime >= seg.start_seconds && currentTime < seg.end_seconds ? 1 : 0.4,
            borderRadius:3,
          }} />
        );
      })}
      <div style={{ position:"absolute", left:`${(currentTime / durSec) * 100}%`, top:3, width:3, height:22, background:"#1e293b", borderRadius:2, transition:"left 0.15s" }} />
    </div>
  );
}

function SegCard({ seg, active, onClick }) {
  const c = TYPES[seg.type] || TYPES.exploration;
  return (
    <div onClick={onClick} style={{
      padding:14, borderRadius:10, cursor:"pointer", transition:"all 0.15s",
      background: active ? c.bg : "#fff", border:`1px solid ${active ? c.border : "#e2e8f0"}`,
    }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6 }}>
        <div><Badge type={seg.type} /><DiffBadge difficulty={seg.difficulty} /></div>
        <span style={{ fontSize:11, color:"#94a3b8", fontFamily:"monospace" }}>{seg.start_label || fmt(seg.start_seconds)}</span>
      </div>
      <div style={{ fontWeight:700, fontSize:14, color:"#1e293b", marginBottom:4 }}>{seg.label}</div>
      <div style={{ fontSize:12, color:"#64748b", lineHeight:1.5 }}>{seg.description}</div>
      {seg.tags && seg.tags.length > 0 && (
        <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginTop:8 }}>
          {seg.tags.map((tag) => (
            <span key={tag} style={{ padding:"1px 6px", borderRadius:999, background:"#f1f5f9", color:"#94a3b8", fontSize:10 }}>#{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/*──────────────────────────── Main App ────────────────────────────*/

export default function App() {
  const [stage, setStage] = useState("pick"); // pick | processing | result
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [walkthrough, setWalkthrough] = useState(null);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState([]);
  const [time, setTime] = useState(0);

  const back = useCallback(() => {
    setStage("pick"); setUrl(""); setErr(""); setWalkthrough(null);
    setSearch(""); setFilters([]); setTime(0); setProgress(0); setStatusMsg("");
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!url.trim()) { setErr("Please enter a URL"); return; }
    setErr(""); setStage("processing"); setProgress(5); setStatusMsg("Starting analysis...");

    try {
      const { job_id, status } = await startAnalysis(url);

      if (status === "complete") {
        // Already analyzed
        const statusData = await (await fetch(`http://localhost:8000/api/status/${job_id}`)).json();
        setWalkthrough(statusData.walkthrough);
        setStage("result");
        return;
      }

      const result = await pollUntilComplete(job_id, (s) => {
        setProgress(s.progress);
        setStatusMsg(s.message);
      });

      setWalkthrough(result);
      setStage("result");
    } catch (e) {
      setErr(e.message || "Analysis failed. Check the URL and try again.");
      setStage("pick");
    }
  }, [url]);

  // Filter segments
  const segments = walkthrough?.segments || [];
  const shown = segments.filter((s) => {
    if (filters.length && !filters.includes(s.type)) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!s.label.toLowerCase().includes(q) && !s.description.toLowerCase().includes(q) &&
          !(s.tags || []).some(t => t.toLowerCase().includes(q))) return false;
    }
    return true;
  });

  /*──── Processing screen ────*/
  if (stage === "processing") {
    return (
      <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
        <Header onBack={back} />
        <div style={{ maxWidth:500, margin:"60px auto", padding:28, borderRadius:14, border:"1px solid #e2e8f0", background:"#fff" }}>
          <div style={{ fontWeight:600, fontSize:14, marginBottom:4 }}>Analyzing video...</div>
          <div style={{ fontSize:12, color:"#6366f1", marginBottom:12, minHeight:16 }}>{statusMsg}</div>
          <Progress pct={progress} />
          <div style={{ marginTop:12, fontSize:11, color:"#94a3b8" }}>
            This usually takes 30-60 seconds depending on video length.
          </div>
        </div>
      </div>
    );
  }

  /*──── Results screen ────*/
  if (stage === "result" && walkthrough) {
    const v = walkthrough.video;
    return (
      <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
        <Header onBack={back} />
        <div style={{ maxWidth:900, margin:"0 auto", padding:"20px 16px" }}>
          <button onClick={back} style={{ padding:"6px 14px", borderRadius:6, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer", fontSize:12, fontWeight:600, color:"#64748b", marginBottom:12 }}>
            Analyze Another Video
          </button>

          <h2 style={{ fontSize:20, fontWeight:800, marginBottom:2 }}>{v.game_title || v.title}</h2>
          <div style={{ fontSize:12, color:"#94a3b8", marginBottom:4 }}>{v.title}</div>
          <div style={{ fontSize:12, color:"#94a3b8", marginBottom:12 }}>{v.channel} | {v.duration_label} | {walkthrough.total_segments} segments</div>

          {/* Summary */}
          <div style={{ background:"#fff", border:"1px solid #e2e8f0", borderRadius:10, padding:16, marginBottom:12, fontSize:13, color:"#475569", lineHeight:1.6 }}>
            {walkthrough.summary}
          </div>

          {/* Player */}
          <div style={{ background:"#1e293b", borderRadius:10, padding:20, textAlign:"center", color:"#94a3b8", marginBottom:8 }}>
            <div style={{ fontSize:18, fontWeight:700, color:"#f1f5f9", marginBottom:4 }}>
              {segments.find(s => time >= s.start_seconds && time < s.end_seconds)?.label || "Click a segment below"}
            </div>
            <div style={{ fontFamily:"monospace", fontSize:13 }}>{fmt(time)} / {v.duration_label}</div>
            <a
              href={`https://youtube.com/watch?v=${v.video_id}&t=${time}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display:"inline-block", marginTop:8, padding:"6px 16px", borderRadius:6, background:"#ef4444", color:"#fff", fontSize:12, fontWeight:600, textDecoration:"none" }}
            >
              Open in YouTube at {fmt(time)}
            </a>
          </div>
          <Timeline segments={segments} durSec={v.duration_seconds} currentTime={time} onSeek={setTime} />

          {/* Stats */}
          <div style={{ display:"flex", gap:12, flexWrap:"wrap", margin:"16px 0 12px", fontSize:12, color:"#64748b" }}>
            {Object.entries(TYPES).map(([t, c]) => {
              const n = segments.filter(s => s.type === t).length;
              return n > 0 ? <span key={t} style={{ color:c.text }}>{c.tag} {n} {c.label}{n > 1 ? "s" : ""}</span> : null;
            })}
          </div>

          {/* Search */}
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search segments... try boss names, areas, items..."
            style={{ width:"100%", padding:"10px 14px", border:"1px solid #e2e8f0", borderRadius:8, fontSize:13, marginBottom:8, boxSizing:"border-box", outline:"none" }} />

          {/* Filters */}
          <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:14 }}>
            {Object.entries(TYPES).map(([t, c]) => {
              const n = segments.filter(s => s.type === t).length;
              if (n === 0) return null;
              const on = filters.includes(t);
              return (
                <button key={t} onClick={() => setFilters(f => on ? f.filter(x => x !== t) : [...f, t])}
                  style={{ padding:"4px 12px", borderRadius:999, border:`1px solid ${on ? c.border : "#d1d5db"}`, background:on ? c.bg : "#fff", color:on ? c.text : "#64748b", fontSize:12, fontWeight:600, cursor:"pointer" }}>
                  {c.label} ({n})
                </button>
              );
            })}
          </div>

          {/* Segments */}
          <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
            {shown.map((seg) => (
              <SegCard key={seg.id} seg={seg}
                active={time >= seg.start_seconds && time < seg.end_seconds}
                onClick={() => setTime(seg.start_seconds)} />
            ))}
            {shown.length === 0 && <div style={{ textAlign:"center", padding:30, color:"#94a3b8" }}>No matching segments.</div>}
          </div>
        </div>
      </div>
    );
  }

  /*──── Pick screen (home) ────*/
  return (
    <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
      <Header onBack={back} />
      <div style={{ maxWidth:600, margin:"0 auto", padding:"48px 16px" }}>
        <div style={{ textAlign:"center", marginBottom:32 }}>
          <h1 style={{ fontSize:28, fontWeight:800, color:"#1e293b", marginBottom:8 }}>
            Paste a YouTube Link.{"\n"}Get a Smart Walkthrough.
          </h1>
          <p style={{ color:"#64748b", fontSize:14, maxWidth:460, margin:"0 auto", lineHeight:1.6 }}>
            Our AI watches the video transcript and automatically identifies boss fights, puzzles,
            collectibles, and more — creating a fully searchable guide.
          </p>
        </div>

        <div style={{ background:"#fff", borderRadius:12, padding:24, border:"1px solid #e2e8f0", marginBottom:20 }}>
          <div style={{ fontWeight:700, fontSize:14, marginBottom:10, color:"#1e293b" }}>Paste a YouTube Video URL</div>
          <div style={{ display:"flex", gap:8 }}>
            <input
              value={url}
              onChange={(e) => { setUrl(e.target.value); setErr(""); }}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
              placeholder="https://youtube.com/watch?v=..."
              style={{ flex:1, padding:"12px 14px", border:"1px solid #e2e8f0", borderRadius:8, fontSize:14, outline:"none" }}
            />
            <button onClick={handleAnalyze}
              style={{ padding:"12px 24px", borderRadius:8, border:"none", background:"#6366f1", color:"#fff", fontWeight:700, fontSize:14, cursor:"pointer", whiteSpace:"nowrap" }}>
              Analyze
            </button>
          </div>
          {err && <div style={{ color:"#ef4444", fontSize:13, marginTop:8 }}>{err}</div>}
          <div style={{ fontSize:12, color:"#94a3b8", marginTop:10 }}>
            Works with any gameplay walkthrough video that has captions/subtitles enabled.
          </div>
        </div>

        {/* How it works */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:12 }}>
          {[
            { step:"1", title:"Paste URL", desc:"Drop any YouTube gameplay video link" },
            { step:"2", title:"AI Analyzes", desc:"Transcript is analyzed for game segments" },
            { step:"3", title:"Get Guide", desc:"Searchable walkthrough with timestamps" },
          ].map(({ step, title, desc }) => (
            <div key={step} style={{ padding:16, borderRadius:10, background:"#fff", border:"1px solid #e2e8f0", textAlign:"center" }}>
              <div style={{ width:28, height:28, borderRadius:999, background:"#6366f1", color:"#fff", fontWeight:700, fontSize:13, display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 8px" }}>{step}</div>
              <div style={{ fontWeight:700, fontSize:13, color:"#1e293b", marginBottom:4 }}>{title}</div>
              <div style={{ fontSize:11, color:"#94a3b8" }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
