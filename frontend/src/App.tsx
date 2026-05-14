import { useCallback, useEffect, useMemo, useState } from "react";
import type { JobStatusResponse, TracksPayload } from "./types";
import VideoPlayerOverlay from "./components/VideoPlayerOverlay";
import MetricsPanel from "./components/MetricsPanel";
import { buildPaths, detectionCounts } from "./lib/tracks";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [labelFile, setLabelFile] = useState<File | null>(null);
  const [taskId, setTaskId] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [tracks, setTracks] = useState<TracksPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<{ weights_exist: boolean; weights_path: string } | null>(null);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [showTrail, setShowTrail] = useState(true);

  useEffect(() => {
    fetchJson<{ weights_exist: boolean; weights_path: string }>("/api/health")
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await fetchJson<JobStatusResponse>(`/api/jobs/${jobId}`);
        if (cancelled) return;
        setStatus(s);
        if (s.status === "done") {
          const t = await fetchJson<TracksPayload>(`/api/jobs/${jobId}/tracks`);
          if (!cancelled) setTracks(t);
        }
        if (s.status === "error") {
          setError(s.error ?? "Job failed");
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void tick();
    const id = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [jobId]);

  const paths = useMemo(() => (tracks ? buildPaths(tracks) : new Map()), [tracks]);
  const counts = useMemo(() => (tracks ? detectionCounts(tracks) : []), [tracks]);

  const onFrameChange = useCallback((frame: number) => {
    setCurrentFrame(frame);
  }, []);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    setTracks(null);
    setJobId(null);
    setCurrentFrame(0);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (labelFile) fd.append("labels", labelFile);
      const tid = taskId.trim();
      if (tid) fd.append("task_id", tid);
      const res = await fetch("/api/jobs", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const body = (await res.json()) as { job_id: string };
      setJobId(body.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const done = status?.status === "done" && tracks && jobId;

  return (
    <div className="app">
      <header className="panel">
        <h1>Salamander video tracker</h1>
        <p className="muted">
          Upload a clip. Run <strong>YOLO</strong> on the server if you have weights, or attach a{" "}
          <strong>Label Studio JSON</strong> export to play your manual <code>videorectangle</code> labels (keyframes are
          interpolated to every frame; rotation is ignored for the drawn box).
        </p>
        {health && (
          <p className="muted" style={{ marginTop: "0.5rem" }}>
            {labelFile ? (
              <>
                Label Studio mode: <strong>no YOLO weights required</strong> for this run. Multipart field name for the
                file: <code>labels</code>.
              </>
            ) : (
              <>
                YOLO weights: {health.weights_exist ? "found" : "missing"} at <code>{health.weights_path}</code>
                {!health.weights_exist && (
                  <>
                    {" "}
                    — add <code>weights/best.pt</code>, set <code>YOLO_WEIGHTS</code>, or upload a Label Studio JSON
                    export.
                  </>
                )}
              </>
            )}
          </p>
        )}
      </header>

      <section className="panel">
        <div className="row" style={{ flexDirection: "column", alignItems: "stretch", gap: "0.5rem" }}>
          <div className="row">
            <span className="muted">Video</span>
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/x-msvideo,video/webm,.mkv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="row">
            <span className="muted">Label Studio JSON (optional)</span>
            <input
              type="file"
              accept=".json,application/json"
              onChange={(e) => setLabelFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="row">
            <label className="muted" htmlFor="taskId" style={{ minWidth: "8rem" }}>
              Task id (optional)
            </label>
            <input
              id="taskId"
              type="text"
              placeholder="e.g. 67 — if the export has multiple tasks"
              value={taskId}
              onChange={(e) => setTaskId(e.target.value)}
              style={{
                flex: 1,
                maxWidth: "24rem",
                padding: "0.35rem 0.5rem",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
              }}
            />
          </div>
          <div className="row">
            <button type="button" disabled={!file || busy} onClick={() => void upload()}>
              {busy ? "Uploading…" : labelFile ? "Build playback from labels" : "Run detection"}
            </button>
          </div>
        </div>
        {jobId && (
          <p style={{ marginTop: "0.75rem" }}>
            Job <code>{jobId}</code> —{" "}
            <span className={`status status-${status?.status ?? "pending"}`}>{status?.status ?? "…"}</span>
          </p>
        )}
        {error && (
          <p className="status status-error" style={{ marginTop: "0.5rem" }}>
            {error}
          </p>
        )}
      </section>

      {done && (
        <>
          <section className="panel">
            <div className="row" style={{ marginBottom: "0.75rem" }}>
              <label className="row">
                <input type="checkbox" checked={showTrail} onChange={(e) => setShowTrail(e.target.checked)} />
                <span>Show path trail</span>
              </label>
            </div>
            <VideoPlayerOverlay
              key={jobId}
              jobId={jobId}
              data={tracks}
              paths={paths}
              currentFrame={currentFrame}
              showTrail={showTrail}
              onFrameChange={onFrameChange}
            />
          </section>
          <section className="panel">
            <MetricsPanel data={tracks} currentFrame={currentFrame} counts={counts} />
          </section>
        </>
      )}
    </div>
  );
}
