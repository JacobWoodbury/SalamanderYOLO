import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FrameTracks, TracksPayload } from "../types";
import { colorForId } from "../lib/tracks";

type Props = {
  data: TracksPayload;
  currentFrame: number;
  counts: { t: number; count: number }[];
};

export default function MetricsPanel({ data, currentFrame, counts }: Props) {
  const frame: FrameTracks | undefined = data.frames[currentFrame];
  const fps = data.meta.fps || 30;

  return (
    <div className="metrics-grid">
      <div className="metric-card">
        <h3>Live box centers (pixels)</h3>
        {!frame || frame.tracks.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No detections in this frame.
          </p>
        ) : (
          <ul className="coords-list">
            {frame.tracks.map((t) => {
              const [x1, y1, x2, y2] = t.xyxy;
              const cx = Math.round((x1 + x2) / 2);
              const cy = Math.round((y1 + y2) / 2);
              return (
                <li key={`${t.id}-${currentFrame}`} style={{ color: colorForId(t.id) }}>
                  Track {t.id}: center ({cx}, {cy})
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="metric-card">
        <h3>Detections on screen over time</h3>
        <p className="muted" style={{ margin: "0 0 0.5rem" }}>
          Frame {currentFrame + 1} / {data.meta.frame_count} — time {(currentFrame / fps).toFixed(2)}s
        </p>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={counts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => `${v}s`} />
              <YAxis allowDecimals={false} width={28} />
              <Tooltip
                formatter={(value: number) => [`${value} salamanders`, "Count"]}
                labelFormatter={(t) => `t = ${Number(t).toFixed(2)} s`}
              />
              <Line type="monotone" dataKey="count" stroke="#0ea5e9" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
