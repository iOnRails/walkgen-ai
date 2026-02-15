import React, { useState, useCallback, useEffect } from "react";
import {
  startAnalysis, pollUntilComplete, getJobStatus, searchYouTube,
  getRecentWalkthroughs, searchBrowse,
  getComments, postComment, toggleReaction,
} from "./api";

/*──────────────────────────── Constants ────────────────────────────*/

const TYPES = {
  boss:        { bg:"#fee2e2", border:"#ef4444", text:"#991b1b", tag:"B", label:"Boss Fight" },
  puzzle:      { bg:"#f3e8ff", border:"#a855f7", text:"#6b21a8", tag:"P", label:"Puzzle" },
  exploration: { bg:"#dbeafe", border:"#3b82f6", text:"#1e3a5f", tag:"E", label:"Exploration" },
  collectible: { bg:"#fef9c3", border:"#eab308", text:"#713f12", tag:"C", label:"Collectible" },
  cutscene:    { bg:"#ccfbf1", border:"#14b8a6", text:"#134e4a", tag:"S", label:"Cutscene" },
  combat:      { bg:"#ffe4e6", border:"#f43f5e", text:"#9f1239", tag:"F", label:"Combat" },
  tutorial:    { bg:"#e0e7ff", border:"#6366f1", text:"#3730a3", tag:"T", label:"Tutorial" },
};

const DIFFS = { easy:"#22c55e", medium:"#eab308", hard:"#f97316", "very hard":"#ef4444", extreme:"#dc2626" };

const REACTION_EMOJIS = [
  { key: "thumbsup", icon: "\uD83D\uDC4D" },
  { key: "fire", icon: "\uD83D\uDD25" },
  { key: "laugh", icon: "\uD83D\uDE02" },
  { key: "heart", icon: "\u2764\uFE0F" },
  { key: "skull", icon: "\uD83D\uDC80" },
  { key: "mind_blown", icon: "\uD83E\uDD2F" },
];

function fmt(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h > 0 ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}` : `${m}:${String(s).padStart(2,"0")}`;
}

function fmtViews(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K`;
  return `${n}`;
}

function timeAgo(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}

const SESSION_ID = Math.random().toString(36).substring(2, 15);

/*──────────────────────────── Small Components ────────────────────────────*/

function Badge({ type }) {
  const c = TYPES[type] || TYPES.exploration;
  return <span style={{ display:"inline-block", padding:"2px 8px", borderRadius:999, fontSize:11, fontWeight:700, background:c.bg, border:`1px solid ${c.border}`, color:c.text }}>{c.tag} {c.label}</span>;
}

function DiffBadge({ difficulty }) {
  if (!difficulty) return null;
  return <span style={{ padding:"2px 7px", borderRadius:999, fontSize:10, fontWeight:700, background:DIFFS[difficulty] || "#94a3b8", color:"#fff", marginLeft:4 }}>{difficulty.toUpperCase()}</span>;
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
      <span style={{ padding:"3px 10px", borderRadius:999, background:"#f0fdf4", border:"1px solid #bbf7d0", color:"#16a34a", fontSize:10, fontWeight:600 }}>Live</span>
    </div>
  );
}

function Timeline({ segments, durSec, currentTime, onSeek }) {
  return (
    <div onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); onSeek(Math.floor(((e.clientX - r.left) / r.width) * durSec)); }}
      style={{ position:"relative", height:28, background:"#e2e8f0", borderRadius:6, cursor:"pointer", marginTop:8 }}>
      {segments.map((seg) => {
        const c = TYPES[seg.type] || TYPES.exploration;
        return <div key={seg.id} title={seg.label} style={{ position:"absolute", left:`${(seg.start_seconds / durSec) * 100}%`, width:`${Math.max(((seg.end_seconds - seg.start_seconds) / durSec) * 100, 0.5)}%`, height:6, top:11, background:c.border, opacity: currentTime >= seg.start_seconds && currentTime < seg.end_seconds ? 1 : 0.4, borderRadius:3 }} />;
      })}
      <div style={{ position:"absolute", left:`${(currentTime / durSec) * 100}%`, top:3, width:3, height:22, background:"#1e293b", borderRadius:2, transition:"left 0.15s" }} />
    </div>
  );
}

function YouTubePlayer({ videoId, startSeconds }) {
  return (
    <div style={{ position:"relative", paddingBottom:"56.25%", height:0, borderRadius:10, overflow:"hidden", marginBottom:8, background:"#000" }}>
      <iframe src={`https://www.youtube.com/embed/${videoId}?start=${startSeconds}&rel=0`}
        title="YouTube player" frameBorder="0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen
        style={{ position:"absolute", top:0, left:0, width:"100%", height:"100%" }} />
    </div>
  );
}

/*──── Comment ────*/
function CommentItem({ comment, videoId, segmentId, onRefresh, depth = 0 }) {
  const [replying, setReplying] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [replyNick, setReplyNick] = useState("");
  const [reactions, setReactions] = useState(comment.reactions || {});

  const handleReact = async (emoji) => {
    try { const d = await toggleReaction(comment.id, emoji, SESSION_ID); setReactions(d.reactions); } catch (e) { console.error(e); }
  };
  const handleReply = async () => {
    if (!replyText.trim()) return;
    try { await postComment(videoId, segmentId, replyText, replyNick, comment.id); setReplyText(""); setReplyNick(""); setReplying(false); onRefresh(); } catch (e) { console.error(e); }
  };

  return (
    <div style={{ marginLeft: depth > 0 ? 24 : 0, marginTop:8 }}>
      <div style={{ padding:10, borderRadius:8, background: depth > 0 ? "#f8fafc" : "#fff", border:"1px solid #e2e8f0" }}>
        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
          <span style={{ fontWeight:600, fontSize:12, color:"#6366f1" }}>{comment.nickname}</span>
          <span style={{ fontSize:10, color:"#94a3b8" }}>{timeAgo(comment.created_at)}</span>
        </div>
        <div style={{ fontSize:13, color:"#1e293b", lineHeight:1.5, marginBottom:6 }}>{comment.text}</div>
        <div style={{ display:"flex", gap:4, flexWrap:"wrap", alignItems:"center" }}>
          {REACTION_EMOJIS.map(({ key, icon }) => {
            const count = reactions[key] || 0;
            return (
              <button key={key} onClick={() => handleReact(key)}
                style={{ padding:"2px 6px", borderRadius:999, border:"1px solid #e2e8f0", background: count > 0 ? "#f0f0ff" : "#fff", fontSize:12, cursor:"pointer", display:"flex", alignItems:"center", gap:2 }}>
                {icon}{count > 0 && <span style={{ fontSize:10, color:"#6366f1" }}>{count}</span>}
              </button>
            );
          })}
          {depth < 2 && <button onClick={() => setReplying(!replying)} style={{ padding:"2px 8px", borderRadius:999, border:"1px solid #e2e8f0", background:"#fff", fontSize:11, color:"#64748b", cursor:"pointer", marginLeft:4 }}>Reply</button>}
        </div>
        {replying && (
          <div style={{ marginTop:8, display:"flex", flexDirection:"column", gap:4 }}>
            <input value={replyNick} onChange={(e) => setReplyNick(e.target.value)} placeholder="Nickname (optional)" style={{ padding:"6px 10px", border:"1px solid #e2e8f0", borderRadius:6, fontSize:12, outline:"none" }} />
            <div style={{ display:"flex", gap:4 }}>
              <input value={replyText} onChange={(e) => setReplyText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleReply()} placeholder="Write a reply..." style={{ flex:1, padding:"6px 10px", border:"1px solid #e2e8f0", borderRadius:6, fontSize:12, outline:"none" }} />
              <button onClick={handleReply} style={{ padding:"6px 14px", borderRadius:6, border:"none", background:"#6366f1", color:"#fff", fontSize:11, fontWeight:600, cursor:"pointer" }}>Send</button>
            </div>
          </div>
        )}
      </div>
      {(comment.replies || []).map((r) => <CommentItem key={r.id} comment={r} videoId={videoId} segmentId={segmentId} onRefresh={onRefresh} depth={depth + 1} />)}
    </div>
  );
}

function CommentsSection({ videoId, segmentId }) {
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [nick, setNick] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    try { const d = await getComments(videoId, segmentId); setComments(d.comments || []); setLoaded(true); } catch (e) { console.error(e); }
  }, [videoId, segmentId]);

  useEffect(() => { if (expanded && !loaded) load(); }, [expanded, loaded, load]);

  const handlePost = async () => {
    if (!text.trim()) return;
    try { await postComment(videoId, segmentId, text, nick); setText(""); load(); } catch (e) { console.error(e); }
  };

  return (
    <div style={{ marginTop:8 }}>
      <button onClick={() => setExpanded(!expanded)} style={{ padding:"4px 10px", borderRadius:6, border:"1px solid #e2e8f0", background:"#f8fafc", fontSize:11, color:"#64748b", cursor:"pointer" }}>
        {expanded ? "Hide Comments" : `Comments${loaded && comments.length > 0 ? ` (${comments.length})` : ""}`}
      </button>
      {expanded && (
        <div style={{ marginTop:8 }}>
          <div style={{ display:"flex", flexDirection:"column", gap:4, marginBottom:8 }}>
            <input value={nick} onChange={(e) => setNick(e.target.value)} placeholder="Nickname (optional)" style={{ padding:"6px 10px", border:"1px solid #e2e8f0", borderRadius:6, fontSize:12, outline:"none", maxWidth:200 }} />
            <div style={{ display:"flex", gap:4 }}>
              <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handlePost()} placeholder="Share a tip, strategy, or question..." style={{ flex:1, padding:"8px 10px", border:"1px solid #e2e8f0", borderRadius:6, fontSize:12, outline:"none" }} />
              <button onClick={handlePost} style={{ padding:"8px 16px", borderRadius:6, border:"none", background:"#6366f1", color:"#fff", fontSize:12, fontWeight:600, cursor:"pointer" }}>Post</button>
            </div>
          </div>
          {comments.length === 0 && loaded && <div style={{ fontSize:12, color:"#94a3b8", padding:8 }}>No comments yet. Be the first!</div>}
          {comments.map((c) => <CommentItem key={c.id} comment={c} videoId={videoId} segmentId={segmentId} onRefresh={load} />)}
        </div>
      )}
    </div>
  );
}

function SegCard({ seg, active, onClick, videoId }) {
  const c = TYPES[seg.type] || TYPES.exploration;
  return (
    <div style={{ borderRadius:10, border:`1px solid ${active ? c.border : "#e2e8f0"}`, background: active ? c.bg : "#fff", overflow:"hidden" }}>
      <div onClick={onClick} style={{ padding:14, cursor:"pointer" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:6 }}>
          <div><Badge type={seg.type} /><DiffBadge difficulty={seg.difficulty} /></div>
          <span style={{ fontSize:11, color:"#94a3b8", fontFamily:"monospace" }}>{seg.start_label || fmt(seg.start_seconds)}</span>
        </div>
        <div style={{ fontWeight:700, fontSize:14, color:"#1e293b", marginBottom:4 }}>{seg.label}</div>
        <div style={{ fontSize:12, color:"#64748b", lineHeight:1.5 }}>{seg.description}</div>
        {seg.tags && seg.tags.length > 0 && (
          <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginTop:8 }}>
            {seg.tags.map((tag) => <span key={tag} style={{ padding:"1px 6px", borderRadius:999, background:"#f1f5f9", color:"#94a3b8", fontSize:10 }}>#{tag}</span>)}
          </div>
        )}
      </div>
      <div style={{ padding:"0 14px 10px" }}><CommentsSection videoId={videoId} segmentId={seg.id} /></div>
    </div>
  );
}

function VideoCard({ video, onAnalyze }) {
  return (
    <div style={{ display:"flex", gap:14, padding:14, borderRadius:10, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer" }}
      onClick={() => onAnalyze(video.url)} onMouseEnter={(e) => e.currentTarget.style.borderColor = "#6366f1"} onMouseLeave={(e) => e.currentTarget.style.borderColor = "#e2e8f0"}>
      {video.thumbnail_url && <div style={{ flexShrink:0, width:160, height:90, borderRadius:8, overflow:"hidden", background:"#1e293b" }}><img src={video.thumbnail_url} alt="" style={{ width:"100%", height:"100%", objectFit:"cover" }} /></div>}
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontWeight:700, fontSize:14, color:"#1e293b", marginBottom:4, overflow:"hidden", textOverflow:"ellipsis", display:"-webkit-box", WebkitLineClamp:2, WebkitBoxOrient:"vertical" }}>{video.title}</div>
        <div style={{ fontSize:12, color:"#64748b", marginBottom:6 }}>{video.channel} {video.duration_label ? `| ${video.duration_label}` : ""} {video.views ? `| ${fmtViews(video.views)} views` : ""}</div>
        <button onClick={(e) => { e.stopPropagation(); onAnalyze(video.url); }} style={{ padding:"6px 16px", borderRadius:6, border:"none", background:"#6366f1", color:"#fff", fontSize:12, fontWeight:600, cursor:"pointer" }}>Analyze This Video</button>
      </div>
    </div>
  );
}

function BrowseCard({ item, onClick }) {
  return (
    <div onClick={onClick} style={{ borderRadius:10, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer", overflow:"hidden" }}
      onMouseEnter={(e) => e.currentTarget.style.borderColor = "#6366f1"} onMouseLeave={(e) => e.currentTarget.style.borderColor = "#e2e8f0"}>
      {item.thumbnail_url && <div style={{ width:"100%", height:120, background:"#1e293b", overflow:"hidden" }}><img src={item.thumbnail_url} alt="" style={{ width:"100%", height:"100%", objectFit:"cover" }} /></div>}
      <div style={{ padding:12 }}>
        <div style={{ fontWeight:700, fontSize:13, color:"#1e293b", marginBottom:4, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{item.game_title || item.video_title}</div>
        <div style={{ fontSize:11, color:"#94a3b8", marginBottom:2 }}>{item.channel} | {item.duration_label}</div>
        <div style={{ fontSize:11, color:"#64748b" }}>{item.total_segments} segments | {item.access_count} views</div>
      </div>
    </div>
  );
}

/*──────────────────────────── Main App ────────────────────────────*/

export default function App() {
  const [stage, setStage] = useState("home");
  const [inputMode, setInputMode] = useState("search");
  const [url, setUrl] = useState("");
  const [aiQuery, setAiQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [walkthrough, setWalkthrough] = useState(null);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState([]);
  const [time, setTime] = useState(0);
  const [recentItems, setRecentItems] = useState([]);
  const [browseQuery, setBrowseQuery] = useState("");
  const [browseResults, setBrowseResults] = useState(null);
  const [homeLoading, setHomeLoading] = useState(true);

  useEffect(() => { getRecentWalkthroughs(12).then((d) => { setRecentItems(d.walkthroughs || []); setHomeLoading(false); }).catch(() => setHomeLoading(false)); }, []);

  const back = useCallback(() => {
    setStage("home"); setUrl(""); setAiQuery(""); setErr(""); setWalkthrough(null);
    setSearch(""); setFilters([]); setTime(0); setProgress(0); setStatusMsg(""); setSearchResults([]); setSearchLoading(false);
    getRecentWalkthroughs(12).then((d) => setRecentItems(d.walkthroughs || [])).catch(() => {});
  }, []);

  const handleSearch = useCallback(async () => {
    if (!aiQuery.trim()) { setErr("Describe what you're looking for"); return; }
    setErr(""); setSearchLoading(true); setSearchResults([]);
    try { const d = await searchYouTube(aiQuery); setSearchResults(d.results || []); if (!(d.results || []).length) setErr("No walkthrough videos found."); }
    catch (e) { setErr(e.message || "Search failed"); } finally { setSearchLoading(false); }
  }, [aiQuery]);

  const handleAnalyze = useCallback(async (videoUrl) => {
    const target = videoUrl || url;
    if (!target.trim()) { setErr("Please enter a URL"); return; }
    setErr(""); setStage("processing"); setProgress(5); setStatusMsg("Starting analysis...");
    try {
      const { job_id, status } = await startAnalysis(target);
      if (status === "complete") { const s = await getJobStatus(job_id); setWalkthrough(s.walkthrough); setStage("result"); return; }
      const result = await pollUntilComplete(job_id, (s) => { setProgress(s.progress); setStatusMsg(s.message); });
      setWalkthrough(result); setStage("result");
    } catch (e) { setErr(e.message || "Analysis failed."); setStage("pick"); }
  }, [url]);

  const handleBrowseSearch = useCallback(async () => {
    if (!browseQuery.trim()) { setBrowseResults(null); return; }
    try { const d = await searchBrowse(browseQuery); setBrowseResults(d.walkthroughs || []); } catch (e) { console.error(e); }
  }, [browseQuery]);

  const segments = walkthrough?.segments || [];
  const shown = segments.filter((s) => {
    if (filters.length && !filters.includes(s.type)) return false;
    if (search) { const q = search.toLowerCase(); return s.label.toLowerCase().includes(q) || s.description.toLowerCase().includes(q) || (s.tags || []).some(t => t.toLowerCase().includes(q)); }
    return true;
  });

  if (stage === "processing") return (
    <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
      <Header onBack={back} />
      <div style={{ maxWidth:500, margin:"60px auto", padding:28, borderRadius:14, border:"1px solid #e2e8f0", background:"#fff" }}>
        <div style={{ fontWeight:600, fontSize:14, marginBottom:4 }}>Analyzing video...</div>
        <div style={{ fontSize:12, color:"#6366f1", marginBottom:12, minHeight:16 }}>{statusMsg}</div>
        <Progress pct={progress} />
        <div style={{ marginTop:12, fontSize:11, color:"#94a3b8" }}>This usually takes 30-60 seconds.</div>
      </div>
    </div>
  );

  if (stage === "result" && walkthrough) {
    const v = walkthrough.video;
    return (
      <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
        <Header onBack={back} />
        <div style={{ maxWidth:900, margin:"0 auto", padding:"20px 16px" }}>
          <button onClick={back} style={{ padding:"6px 14px", borderRadius:6, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer", fontSize:12, fontWeight:600, color:"#64748b", marginBottom:12 }}>Back to Home</button>
          <h2 style={{ fontSize:20, fontWeight:800, marginBottom:2 }}>{v.game_title || v.title}</h2>
          <div style={{ fontSize:12, color:"#94a3b8", marginBottom:4 }}>{v.title}</div>
          <div style={{ fontSize:12, color:"#94a3b8", marginBottom:12 }}>{v.channel} | {v.duration_label} | {walkthrough.total_segments} segments</div>
          <div style={{ background:"#fff", border:"1px solid #e2e8f0", borderRadius:10, padding:16, marginBottom:12, fontSize:13, color:"#475569", lineHeight:1.6 }}>{walkthrough.summary}</div>
          <YouTubePlayer videoId={v.video_id} startSeconds={time} />
          <Timeline segments={segments} durSec={v.duration_seconds} currentTime={time} onSeek={setTime} />
          <div style={{ display:"flex", gap:12, flexWrap:"wrap", margin:"16px 0 12px", fontSize:12, color:"#64748b" }}>
            {Object.entries(TYPES).map(([t, c]) => { const n = segments.filter(s => s.type === t).length; return n > 0 ? <span key={t} style={{ color:c.text }}>{c.tag} {n} {c.label}{n > 1 ? "s" : ""}</span> : null; })}
          </div>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search segments..." style={{ width:"100%", padding:"10px 14px", border:"1px solid #e2e8f0", borderRadius:8, fontSize:13, marginBottom:8, boxSizing:"border-box", outline:"none" }} />
          <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:14 }}>
            {Object.entries(TYPES).map(([t, c]) => { const n = segments.filter(s => s.type === t).length; if (!n) return null; const on = filters.includes(t); return (
              <button key={t} onClick={() => setFilters(f => on ? f.filter(x => x !== t) : [...f, t])} style={{ padding:"4px 12px", borderRadius:999, border:`1px solid ${on ? c.border : "#d1d5db"}`, background:on ? c.bg : "#fff", color:on ? c.text : "#64748b", fontSize:12, fontWeight:600, cursor:"pointer" }}>{c.label} ({n})</button>
            ); })}
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
            {shown.map((seg) => <SegCard key={seg.id} seg={seg} videoId={v.video_id} active={time >= seg.start_seconds && time < seg.end_seconds} onClick={() => setTime(seg.start_seconds)} />)}
            {!shown.length && <div style={{ textAlign:"center", padding:30, color:"#94a3b8" }}>No matching segments.</div>}
          </div>
        </div>
      </div>
    );
  }

  if (stage === "pick") return (
    <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
      <Header onBack={back} />
      <div style={{ maxWidth:600, margin:"0 auto", padding:"32px 16px" }}>
        <button onClick={back} style={{ padding:"6px 14px", borderRadius:6, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer", fontSize:12, fontWeight:600, color:"#64748b", marginBottom:16 }}>Back to Home</button>
        <div style={{ display:"flex", gap:0, marginBottom:0 }}>
          <button onClick={() => setInputMode("search")} style={{ flex:1, padding:"10px 0", border:"1px solid #e2e8f0", borderBottom: inputMode === "search" ? "2px solid #6366f1" : "1px solid #e2e8f0", background: inputMode === "search" ? "#fff" : "#f8fafc", color: inputMode === "search" ? "#6366f1" : "#94a3b8", fontWeight:700, fontSize:13, cursor:"pointer", borderRadius:"8px 0 0 0" }}>AI Search</button>
          <button onClick={() => setInputMode("url")} style={{ flex:1, padding:"10px 0", border:"1px solid #e2e8f0", borderBottom: inputMode === "url" ? "2px solid #6366f1" : "1px solid #e2e8f0", background: inputMode === "url" ? "#fff" : "#f8fafc", color: inputMode === "url" ? "#6366f1" : "#94a3b8", fontWeight:700, fontSize:13, cursor:"pointer", borderRadius:"0 8px 0 0" }}>Paste URL</button>
        </div>
        <div style={{ background:"#fff", borderRadius:"0 0 12px 12px", padding:24, border:"1px solid #e2e8f0", borderTop:"none", marginBottom:20 }}>
          {inputMode === "search" ? (<>
            <div style={{ fontWeight:700, fontSize:14, marginBottom:10, color:"#1e293b" }}>What do you need a walkthrough for?</div>
            <div style={{ display:"flex", gap:8 }}>
              <input value={aiQuery} onChange={(e) => { setAiQuery(e.target.value); setErr(""); }} onKeyDown={(e) => e.key === "Enter" && handleSearch()} placeholder='"how to collect insult lines in Monkey Island"' style={{ flex:1, padding:"12px 14px", border:"1px solid #e2e8f0", borderRadius:8, fontSize:14, outline:"none" }} />
              <button onClick={handleSearch} disabled={searchLoading} style={{ padding:"12px 24px", borderRadius:8, border:"none", background: searchLoading ? "#a5b4fc" : "#6366f1", color:"#fff", fontWeight:700, fontSize:14, cursor: searchLoading ? "wait" : "pointer", whiteSpace:"nowrap" }}>{searchLoading ? "Searching..." : "Find Videos"}</button>
            </div>
            {!searchResults.length && !searchLoading && !err && (
              <div style={{ marginTop:12, display:"flex", flexWrap:"wrap", gap:6 }}>
                <span style={{ fontSize:11, color:"#94a3b8", lineHeight:"26px" }}>Try:</span>
                {["Elden Ring beat Malenia", "Zelda TotK shrine locations", "Monkey Island insult sword fighting", "BG3 Shadowheart quest"].map((q) => (
                  <button key={q} onClick={() => setAiQuery(q)} style={{ padding:"4px 10px", borderRadius:999, border:"1px solid #e2e8f0", background:"#f8fafc", color:"#64748b", fontSize:11, cursor:"pointer" }}>{q}</button>
                ))}
              </div>
            )}
          </>) : (<>
            <div style={{ fontWeight:700, fontSize:14, marginBottom:10, color:"#1e293b" }}>Paste a YouTube Video URL</div>
            <div style={{ display:"flex", gap:8 }}>
              <input value={url} onChange={(e) => { setUrl(e.target.value); setErr(""); }} onKeyDown={(e) => e.key === "Enter" && handleAnalyze()} placeholder="https://youtube.com/watch?v=..." style={{ flex:1, padding:"12px 14px", border:"1px solid #e2e8f0", borderRadius:8, fontSize:14, outline:"none" }} />
              <button onClick={() => handleAnalyze()} style={{ padding:"12px 24px", borderRadius:8, border:"none", background:"#6366f1", color:"#fff", fontWeight:700, fontSize:14, cursor:"pointer", whiteSpace:"nowrap" }}>Analyze</button>
            </div>
          </>)}
          {err && <div style={{ color:"#ef4444", fontSize:13, marginTop:8 }}>{err}</div>}
        </div>
        {searchResults.length > 0 && (
          <div style={{ marginBottom:20 }}>
            <div style={{ fontWeight:700, fontSize:14, color:"#1e293b", marginBottom:10 }}>Found {searchResults.length} walkthrough videos:</div>
            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>{searchResults.map((v) => <VideoCard key={v.video_id} video={v} onAnalyze={handleAnalyze} />)}</div>
          </div>
        )}
      </div>
    </div>
  );

  /* ──── Homepage ──── */
  return (
    <div style={{ minHeight:"100vh", background:"#f8fafc", fontFamily:"system-ui, sans-serif" }}>
      <Header onBack={back} />
      <div style={{ maxWidth:900, margin:"0 auto", padding:"32px 16px" }}>
        <div style={{ textAlign:"center", marginBottom:32 }}>
          <h1 style={{ fontSize:28, fontWeight:800, color:"#1e293b", marginBottom:8 }}>AI-Powered Game Walkthroughs</h1>
          <p style={{ color:"#64748b", fontSize:14, maxWidth:500, margin:"0 auto 20px", lineHeight:1.6 }}>Describe what you need or paste a YouTube link. AI analyzes the video and creates a searchable guide with boss fights, puzzles, collectibles, and more.</p>
          <button onClick={() => setStage("pick")} style={{ padding:"14px 32px", borderRadius:10, border:"none", background:"#6366f1", color:"#fff", fontWeight:700, fontSize:16, cursor:"pointer" }}>Analyze a New Video</button>
        </div>

        {recentItems.length > 0 && (<>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
            <h2 style={{ fontSize:18, fontWeight:700, color:"#1e293b" }}>Recently Analyzed</h2>
            <div style={{ display:"flex", gap:6 }}>
              <input value={browseQuery} onChange={(e) => setBrowseQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleBrowseSearch()} placeholder="Filter by game..." style={{ padding:"6px 12px", border:"1px solid #e2e8f0", borderRadius:6, fontSize:12, outline:"none", width:180 }} />
              <button onClick={handleBrowseSearch} style={{ padding:"6px 14px", borderRadius:6, border:"1px solid #e2e8f0", background:"#fff", fontSize:12, fontWeight:600, color:"#64748b", cursor:"pointer" }}>Filter</button>
              {browseResults && <button onClick={() => { setBrowseResults(null); setBrowseQuery(""); }} style={{ padding:"6px 10px", borderRadius:6, border:"1px solid #e2e8f0", background:"#fff", fontSize:12, color:"#ef4444", cursor:"pointer" }}>Clear</button>}
            </div>
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(200px, 1fr))", gap:12, marginBottom:32 }}>
            {(browseResults || recentItems).map((item) => <BrowseCard key={item.video_id} item={item} onClick={() => handleAnalyze(`https://www.youtube.com/watch?v=${item.video_id}`)} />)}
            {browseResults && !browseResults.length && <div style={{ gridColumn:"1/-1", textAlign:"center", padding:30, color:"#94a3b8" }}>No matches found.</div>}
          </div>
        </>)}

        <div style={{ display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:12 }}>
          {[
            { step:"1", title:"Describe or Paste", desc:"Tell AI what walkthrough you need, or paste a YouTube URL" },
            { step:"2", title:"AI Analyzes", desc:"Video transcript is analyzed for boss fights, puzzles, and more" },
            { step:"3", title:"Get Guide", desc:"Searchable walkthrough with timestamps, comments, and reactions" },
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
